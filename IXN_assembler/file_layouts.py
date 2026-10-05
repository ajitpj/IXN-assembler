'''Infer which image files make up each timelapse stack, from file names alone.

Three on-disk layouts are supported:

legacy          MetaXpress 'TimePoint_N' folders, one per timepoint, holding
                files named  <name>_<well>_<site>_w<N><GUID>.tif
                e.g.  TimePoint_7/pFF1-CycB_A06_s1_w1A3F2...C9.tif

time_folders    One folder per timepoint, named <text><digits> (the digits are
                the timepoint), holding files with the new naming scheme below.
                e.g.  Timepoint_7/Plate_c10_r05_sc02_sr05_w01_z01.tif

single_folder   Every image of the experiment in one folder, which may sit one
                or two levels below the selected folder. The timepoint comes
                from the _t token of the new naming scheme.
                e.g.  Plate/Plate_c10_r05_sc02_sr05_w01_t074_z01.tif

New naming scheme:  <name>_c<col>_r<row>_sc<site col>_sr<site row>_w<N>[_t<N>][_z<N>].tif
  c10_r05 is well E10 (r = plate row, c = plate column); sc/sr place the site
  within the well.

Each indexer returns a StackIndex mapping (well, position, wavelength) to the
frames of that stack in timepoint order. Nothing here opens an image, so the
functions run on empty placeholder files (see tests/).
'''
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NamedTuple, Optional

LAYOUTS = ('legacy', 'time_folders', 'single_folder')
LAYOUT_LABELS = {'legacy': 'Legacy',
                 'time_folders': 'Organized by time',
                 'single_folder': 'Single-folder storage'}

NEW_NAME_RE = re.compile(
    r'^(?P<name>.+?)'
    r'_c(?P<col>\d+)_r(?P<row>\d+)'
    r'_sc(?P<site_col>\d+)_sr(?P<site_row>\d+)'
    r'_w(?P<wavelength>\d+)'
    r'(?:_t(?P<timepoint>\d+))?'
    r'(?:_z(?P<z>\d+))?'
    r'\.tiff?$',
    re.IGNORECASE)

# Mirrors the original split('_') parsing: name, well, site, and the two
# characters 'wN' at the start of the fourth field (a GUID follows them).
LEGACY_NAME_RE = re.compile(
    r'^(?P<name>[^_]+)_(?P<well>[^_]+)_(?P<site>[^_]+)_(?P<wavelength>w\d)',
    re.IGNORECASE)

# 'TimePoint_12' -> ('TimePoint_', '12'); a name with no text prefix is not one
TIME_DIR_RE = re.compile(r'^(?P<prefix>.*\D)(?P<timepoint>\d+)$')


class Frame(NamedTuple):
    timepoint: int
    path: Path


@dataclass
class StackIndex:
    name: str
    # (well, position, wavelength) -> frames sorted by timepoint
    stacks: dict = field(default_factory=dict)

    @property
    def wells(self) -> list:
        return sorted({well for well, _, _ in self.stacks})

    @property
    def positions(self) -> list:
        return sorted({pos for _, pos, _ in self.stacks})

    @property
    def wavelengths(self) -> list:
        return sorted({w for _, _, w in self.stacks})

    @property
    def timepoints(self) -> list:
        return sorted({f.timepoint for frames in self.stacks.values()
                       for f in frames})

    def files(self, well: str, position: str, wavelength: str) -> list:
        '''Paths of one stack in timepoint order; empty if it does not exist.'''
        return [f.path for f in self.stacks.get((well, position, wavelength), [])]

    def first_file(self, wavelength: Optional[str] = None) -> Path:
        '''Earliest frame of the first stack (for a wavelength, if given).'''
        for (_, _, w), frames in sorted(self.stacks.items()):
            if wavelength is None or w == wavelength:
                return frames[0].path
        raise KeyError(wavelength)


def is_image_file(path: Path) -> bool:
    '''IXN image, thumbnails excluded.'''
    return (path.suffix.casefold() in ('.tif', '.tiff')
            and 'thumb' not in path.name.casefold())


def well_label(row: int, col: int) -> str:
    '''Plate row/column to a well name: (5, 10) -> 'E10'. Rows past Z continue
    as AA, AB, ... as on 1536-well plates.'''
    letters = ''
    while row > 0:
        row, rem = divmod(row - 1, 26)
        letters = chr(ord('A') + rem) + letters
    return f'{letters}{col:02d}'


def parse_new_filename(filename: str) -> Optional[dict]:
    '''Fields of a new-scheme file name, or None if it does not match.

    Returns name, well, position, wavelength, and timepoint / z as ints
    (None when the token is absent).'''
    m = NEW_NAME_RE.match(filename)
    if not m:
        return None
    g = m.groupdict()
    return {
        'name': g['name'],
        'well': well_label(int(g['row']), int(g['col'])),
        'position': f"sc{g['site_col']}sr{g['site_row']}",
        'wavelength': 'w' + g['wavelength'],
        'timepoint': int(g['timepoint']) if g['timepoint'] else None,
        'z': int(g['z']) if g['z'] else None,
    }


def parse_legacy_filename(filename: str) -> Optional[dict]:
    '''Fields of a legacy MetaXpress file name, or None if it does not match.'''
    m = LEGACY_NAME_RE.match(filename)
    if not m:
        return None
    return {'name': m['name'], 'well': m['well'], 'position': m['site'],
            'wavelength': m['wavelength'], 'timepoint': None, 'z': None}


def parse_any_filename(filename: str) -> Optional[dict]:
    return parse_new_filename(filename) or parse_legacy_filename(filename)


def _walk_dirs(root: Path, max_depth: int):
    '''Yield root and its subdirectories down to max_depth levels below it.'''
    root = Path(root)
    pending = [(root, 0)]
    while pending:
        directory, depth = pending.pop()
        yield directory
        if depth < max_depth:
            with os.scandir(directory) as entries:
                pending.extend((Path(e.path), depth + 1) for e in entries
                               if e.is_dir() and not e.name.startswith('.'))


def _image_files(directory: Path) -> list:
    with os.scandir(directory) as entries:
        return [Path(e.path) for e in entries
                if e.is_file() and is_image_file(Path(e.name))]


def _build_index(records: list) -> Optional[StackIndex]:
    '''records: (parsed fields with an int timepoint, path). Groups them into
    stacks and sorts each one by timepoint.'''
    if not records:
        return None

    names = sorted({fields['name'] for fields, _ in records})
    if len(names) > 1:
        raise ValueError(f'Images from more than one experiment: {names}')

    # Keep z out of the position name unless there is more than one plane:
    # each z-plane then becomes its own (t, y, x) stack.
    multi_z = len({fields['z'] for fields, _ in records}) > 1

    stacks = defaultdict(list)
    for fields, path in records:
        position = fields['position']
        if multi_z:
            position += f"z{fields['z'] or 0:02d}"
        key = (fields['well'], position, fields['wavelength'])
        stacks[key].append(Frame(fields['timepoint'], path))

    for key, frames in stacks.items():
        frames.sort()
        seen = Counter(f.timepoint for f in frames)
        dupes = sorted(t for t, n in seen.items() if n > 1)
        if dupes:
            examples = [str(f.path) for f in frames if f.timepoint == dupes[0]]
            raise ValueError(f'{key}: more than one image for timepoint(s) '
                             f'{dupes}, e.g. {examples}')

    return StackIndex(names[0], dict(stacks))


def find_time_dirs(data_dir: Path, prefix: Optional[str] = None,
                   max_depth: int = 1) -> dict:
    '''{timepoint: directory} for folders named <text><digits>.

    Time folders are looked for 1 to max_depth levels below data_dir; the
    search does not descend into them. If prefix is None, the largest series
    of sibling folders sharing a text prefix wins, so a stray 'Plate2' folder
    next to 'Timepoint_1'..'Timepoint_90' is ignored.'''
    by_prefix = defaultdict(list)
    pending = [(Path(data_dir), 0)]
    while pending:
        directory, depth = pending.pop()
        with os.scandir(directory) as entries:
            subdirs = [Path(e.path) for e in entries
                       if e.is_dir() and not e.name.startswith('.')]
        for sub in subdirs:
            m = TIME_DIR_RE.match(sub.name)
            if m and (prefix is None
                      or m['prefix'].casefold() == prefix.casefold()):
                # (parent, prefix) so two runs in sibling folders stay apart
                by_prefix[(directory, m['prefix'])].append(
                    (int(m['timepoint']), sub))
            elif depth + 1 < max_depth:
                # time folders sit at most max_depth levels down
                pending.append((sub, depth + 1))

    if not by_prefix:
        return {}
    series = max(by_prefix.values(), key=len)
    time_dirs = {}
    for timepoint, directory in series:
        if timepoint in time_dirs:
            raise ValueError(f'Two folders for timepoint {timepoint}: '
                             f'{time_dirs[timepoint]} and {directory}')
        time_dirs[timepoint] = directory
    return time_dirs


def _index_time_dirs(time_dirs: dict, parse: Callable) -> Optional[StackIndex]:
    records = []
    for timepoint, directory in time_dirs.items():
        for path in _image_files(directory):
            fields = parse(path.name)
            if fields is None:
                continue
            # the folder, not any _t token in the file name, sets the timepoint
            records.append(({**fields, 'timepoint': timepoint}, path))
    return _build_index(records)


def index_legacy(data_dir: Path) -> Optional[StackIndex]:
    '''Legacy layout: data_dir/TimePoint_<N>/<name>_<well>_<site>_w<N><GUID>.tif'''
    time_dirs = find_time_dirs(data_dir, prefix='TimePoint_', max_depth=1)
    return _index_time_dirs(time_dirs, parse_legacy_filename)


def index_time_folders(data_dir: Path, max_depth: int = 2) -> Optional[StackIndex]:
    '''Organized-by-time layout: one <text><digits> folder per timepoint,
    found at most max_depth levels below data_dir.

    Files are expected to use the new naming scheme (with or without a _t
    token); legacy-style names are accepted as a fallback. The timepoint is
    taken from the folder name.'''
    time_dirs = find_time_dirs(data_dir, max_depth=max_depth)
    return _index_time_dirs(time_dirs, parse_any_filename)


def index_single_folder(data_dir: Path, max_depth: int = 2) -> Optional[StackIndex]:
    '''Single-folder layout: every image in one folder, data_dir itself or up
    to max_depth levels below it. Timepoints come from the _t token.

    Raises ValueError if images turn up in more than one folder.'''
    found = {}
    for directory in _walk_dirs(data_dir, max_depth):
        records = []
        for path in _image_files(directory):
            fields = parse_new_filename(path.name)
            if fields is not None and fields['timepoint'] is not None:
                records.append((fields, path))
        if records:
            found[directory] = records

    if len(found) > 1:
        raise ValueError('Images found in more than one folder: '
                         + ', '.join(sorted(str(d) for d in found))
                         + '. Select the folder that holds them.')
    if not found:
        return None
    return _build_index(next(iter(found.values())))


INDEXERS = {
    'legacy': index_legacy,
    'time_folders': index_time_folders,
    'single_folder': index_single_folder,
}


def build_index(data_dir: Path, layout: str) -> Optional[StackIndex]:
    '''Index data_dir according to layout (one of LAYOUTS). Returns None when
    no matching images are found.'''
    if layout not in INDEXERS:
        raise ValueError(f'Unknown layout {layout!r}; expected one of {LAYOUTS}')
    return INDEXERS[layout](Path(data_dir))
