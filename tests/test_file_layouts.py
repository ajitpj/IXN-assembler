'''Unit tests for IXN_assembler.file_layouts.

The indexers only look at names, so the synthetic datasets here are trees of
empty files. Run from the repository root with either

    python -m unittest discover -s tests -v
    python -m pytest tests            (if pytest is installed)

TestRealData additionally checks a real single-folder experiment. It runs only
when that folder is reachable; point IXN_SINGLE_FOLDER_DATA (and, for the
legacy check, IXN_LEGACY_DATA) at other datasets to validate them too.
'''
import os
import random
import re
import tempfile
import unittest
from pathlib import Path

from IXN_assembler.file_layouts import (
    build_index, downstream_incompatible, find_time_dirs, index_legacy,
    index_single_folder, index_time_folders, parse_legacy_filename,
    parse_new_filename, well_label)

PLATE = 'Mia-Panc-Huh Noco-GSK'   # real plate name: has spaces and dashes


def new_name(col, row, sc, sr, w, t=None, z=1, plate=PLATE):
    name = f'{plate}_c{col:02d}_r{row:02d}_sc{sc:02d}_sr{sr:02d}_w{w:02d}'
    if t is not None:
        name += f'_t{t:03d}'
    if z is not None:
        name += f'_z{z:02d}'
    return name + '.tif'


def touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


class TmpDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestFilenameParsing(unittest.TestCase):

    def test_new_scheme_example(self):
        f = parse_new_filename(new_name(10, 5, 2, 5, 1, t=74))
        self.assertEqual(f, {'name': PLATE, 'well': 'E10', 'position': None,
                             'site_grid': (5, 2),
                             'wavelength': 'w01', 'timepoint': 74, 'z': 1})

    def test_new_scheme_without_t_or_z(self):
        f = parse_new_filename('Plate_c03_r02_sc01_sr01_w02.tif')
        self.assertEqual((f['well'], f['wavelength'], f['timepoint'], f['z']),
                         ('B03', 'w02', None, None))

    def test_plate_name_with_underscores(self):
        f = parse_new_filename('my_plate_2_c01_r01_sc01_sr01_w01_t001_z01.tif')
        self.assertEqual(f['name'], 'my_plate_2')

    def test_extension_case_and_tiff(self):
        self.assertIsNotNone(parse_new_filename('P_c01_r01_sc01_sr01_w01_t1.TIF'))
        self.assertIsNotNone(parse_new_filename('P_c01_r01_sc01_sr01_w01_t1.tiff'))

    def test_non_matching_names(self):
        for name in ['notes.txt', 'P_c01_r01_w01_t001.tif',
                     'P_c01_r01_sc01_sr01_w01_t001_z01.png',
                     '20250612_A10_s1_w18942BF42-9FCF.tif']:
            self.assertIsNone(parse_new_filename(name), name)

    def test_unpadded_numbers(self):
        f = parse_new_filename('P_c5_r3_sc1_sr2_w1_t9_z1.tif')
        self.assertEqual((f['well'], f['site_grid'], f['timepoint']),
                         ('C05', (2, 1), 9))

    def test_legacy_scheme(self):
        f = parse_legacy_filename('20250612_A10_s1_w18942BF42-9FCF-40D3-937C-2D51B516160F.tif')
        self.assertEqual((f['name'], f['well'], f['position'], f['wavelength']),
                         ('20250612', 'A10', 's1', 'w1'))
        self.assertIsNone(parse_legacy_filename('notes.txt'))

    def test_well_label(self):
        self.assertEqual(well_label(1, 1), 'A01')
        self.assertEqual(well_label(5, 10), 'E10')
        self.assertEqual(well_label(8, 12), 'H12')
        self.assertEqual(well_label(16, 24), 'P24')
        self.assertEqual(well_label(27, 48), 'AA48')
        self.assertEqual(well_label(32, 48), 'AF48')


class TestSingleFolder(TmpDirTestCase):

    def make(self, folder: Path, timepoints, sites=((2, 5), (7, 6)),
             wells=((10, 5), (11, 1)), wavelengths=(1,)):
        names = [new_name(c, r, sc, sr, w, t)
                 for c, r in wells for sc, sr in sites
                 for w in wavelengths for t in timepoints]
        random.Random(0).shuffle(names)     # creation order must not matter
        for n in names:
            touch(folder / n)

    def test_stacks_are_sorted_by_timepoint(self):
        self.make(self.root / PLATE, timepoints=range(1, 134))
        ix = index_single_folder(self.root)
        self.assertEqual(ix.name, PLATE)
        self.assertEqual(ix.wells, ['A11', 'E10'])
        self.assertEqual(ix.positions, ['s1', 's2'])
        self.assertEqual(ix.wavelengths, ['w01'])
        self.assertEqual(ix.timepoints, list(range(1, 134)))
        self.assertEqual(len(ix.stacks), 4)
        files = ix.files('E10', 's1', 'w01')
        self.assertEqual([f.name for f in files],
                         [new_name(10, 5, 2, 5, 1, t) for t in range(1, 134)])

    def test_numeric_not_string_order(self):
        # t9 < t10 < t100 even without zero padding
        for t in (100, 9, 10, 1):
            touch(self.root / f'P_c01_r01_sc01_sr01_w01_t{t}_z01.tif')
        ix = index_single_folder(self.root)
        self.assertEqual([f.timepoint for f in ix.stacks[('A01', 's1', 'w01')]],
                         [1, 9, 10, 100])

    def test_found_one_or_two_levels_down(self):
        for sub in ['', 'plate', 'run/plate']:
            with self.subTest(sub=sub), tempfile.TemporaryDirectory() as d:
                self.make(Path(d) / sub, timepoints=[1, 2, 3])
                ix = index_single_folder(Path(d))
                self.assertEqual(len(ix.stacks), 4)
                self.assertEqual(ix.timepoints, [1, 2, 3])

    def test_too_deep_is_not_found(self):
        self.make(self.root / 'a' / 'b' / 'c', timepoints=[1, 2])
        self.assertIsNone(index_single_folder(self.root))
        self.assertIsNotNone(index_single_folder(self.root, max_depth=3))

    def test_multiple_wavelengths(self):
        self.make(self.root, timepoints=[1, 2], wavelengths=(1, 2, 3))
        ix = index_single_folder(self.root)
        self.assertEqual(ix.wavelengths, ['w01', 'w02', 'w03'])
        self.assertEqual(len(ix.stacks), 12)
        # wells sort A11 < E10, so the first w02 stack is A11's
        self.assertEqual(ix.first_file('w02').name, new_name(11, 1, 2, 5, 2, 1))

    def test_missing_timepoint_gives_shorter_stack(self):
        self.make(self.root, timepoints=[1, 2, 3, 4])
        (self.root / new_name(10, 5, 2, 5, 1, 3)).unlink()
        ix = index_single_folder(self.root)
        self.assertEqual([f.timepoint for f in ix.stacks[('E10', 's1', 'w01')]],
                         [1, 2, 4])
        self.assertEqual(ix.timepoints, [1, 2, 3, 4])

    def test_ignores_thumbs_other_files_and_names_without_t(self):
        self.make(self.root, timepoints=[1, 2])
        touch(self.root / 'P_c01_r01_sc01_sr01_w01_t001_z01_thumb.tif')
        touch(self.root / 'P_c01_r01_sc01_sr01_w01_z01.tif')   # no timepoint
        touch(self.root / 'platemap.xlsx')
        touch(self.root / '20261002_Plate_E10_s1_phs.tif')  # an output stack
        ix = index_single_folder(self.root)
        self.assertEqual(len(ix.stacks), 4)

    def test_multiple_z_planes_become_separate_stacks(self):
        for z in (1, 2):
            for t in (1, 2):
                touch(self.root / new_name(1, 1, 1, 1, 1, t, z=z))
        ix = index_single_folder(self.root)
        self.assertEqual(ix.positions, ['s1_z01', 's1_z02'])
        self.assertEqual(len(ix.files('A01', 's1_z02', 'w01')), 2)

    def test_site_numbers_follow_the_site_grid_row_by_row(self):
        # the 20261002 site pattern; the stage labels there read
        # sc02_sr05 -> 'Site 5' and sc05_sr08 -> 'Site 9'
        sites = [(2, 2), (2, 3), (2, 5), (2, 7), (4, 3), (5, 5), (5, 8), (7, 3), (7, 6)]
        self.make(self.root, timepoints=[1], sites=sites, wells=((10, 5),))
        ix = index_single_folder(self.root)
        self.assertEqual(ix.positions, [f's{n}' for n in range(1, 10)])
        site_of = {f.path.name.split('_sc')[1][:7]: pos
                   for (_, pos, _), frames in ix.stacks.items() for f in frames}
        self.assertEqual(site_of['02_sr02'], 's1')
        self.assertEqual(site_of['02_sr05'], 's5')
        self.assertEqual(site_of['05_sr08'], 's9')
        self.assertEqual(site_of['07_sr06'], 's7')

    def test_subset_of_sites_is_numbered_by_what_is_present(self):
        # with only 2 of the 9 sites, the names alone give s1, s2; the GUI
        # then renames them from the stage labels (IXN_funcs.metadata_site_names)
        self.make(self.root, timepoints=[1], sites=[(2, 5), (7, 6)], wells=((10, 5),))
        ix = index_single_folder(self.root)
        self.assertEqual(ix.positions, ['s1', 's2'])
        ix.rename_positions({'s1': 's5', 's2': 's7'})
        self.assertEqual(ix.positions, ['s5', 's7'])
        self.assertEqual(ix.files('E10', 's5', 'w01')[0].name, new_name(10, 5, 2, 5, 1, 1))

    def test_rename_positions_refuses_to_merge_stacks(self):
        self.make(self.root, timepoints=[1], sites=[(2, 5), (7, 6)], wells=((10, 5),))
        ix = index_single_folder(self.root)
        with self.assertRaises(ValueError):
            ix.rename_positions({'s1': 's2'})

    def test_positions_sort_numerically(self):
        sites = [(sc, 1) for sc in range(1, 12)]
        self.make(self.root, timepoints=[1], sites=sites, wells=((1, 1),))
        self.assertEqual(index_single_folder(self.root).positions,
                         [f's{n}' for n in range(1, 12)])

    def test_images_in_two_folders_is_an_error(self):
        self.make(self.root / 'a', timepoints=[1])
        self.make(self.root / 'b', timepoints=[2])
        with self.assertRaises(ValueError):
            index_single_folder(self.root)

    def test_two_experiments_is_an_error(self):
        touch(self.root / new_name(1, 1, 1, 1, 1, 1, plate='A'))
        touch(self.root / new_name(1, 1, 1, 1, 1, 1, plate='B'))
        with self.assertRaises(ValueError):
            index_single_folder(self.root)

    def test_empty_folder(self):
        self.assertIsNone(index_single_folder(self.root))


class TestDownstreamNames(TmpDirTestCase):
    '''Stack names must parse with the regexes cellapp-analysis uses.'''

    # copied from cellapp-analysis pipeline.py and cellaap_analysis.py
    PIPELINE_STUB_RE = re.compile(
        r"(?P<well>[A-H](?:0[1-9]|1[0-2]|[1-9]))_s(?P<site>\d{1,2})")
    ANALYSIS_STUB_RE = re.compile(r"[A-H]([1-9]|[0][1-9]|[1][0-2])_s(\d{2}|\d{1})")
    CHANNEL_RE = re.compile(r"GFP|Texas Red|Cy5|phs")

    def stack_name(self, ix, well, pos, channel, date='20261002'):
        # as IXN_funcs.write_all_stacks names them
        return f'{date}_{ix.name}_{well}_{pos}_{channel}.tif'

    def test_new_scheme_stack_names_parse(self):
        for t in (1, 2):
            for sc, sr in ((2, 5), (7, 6)):
                touch(self.root / new_name(10, 5, sc, sr, 1, t))
        ix = index_single_folder(self.root)
        for well, pos, _ in ix.stacks:
            for channel in ('phs', 'GFP', 'Texas Red'):
                name = self.stack_name(ix, well, pos, channel)
                m = self.PIPELINE_STUB_RE.search(name)
                self.assertEqual((m['well'], m['site']), (well, pos[1:]), name)
                stub = self.ANALYSIS_STUB_RE.search(name).group()
                self.assertEqual(stub, f'{well}_{pos}')
                # cellaap_analysis.files: stub + '_' in the name, then a channel
                self.assertIn(stub + '_', name)
                self.assertEqual(self.CHANNEL_RE.search(name).group(), channel)
                # pipeline/create_correction_maps take the channel from the stem
                self.assertEqual(Path(name).stem.split('_')[-1], channel)
                # cellaap_analysis.expt_name
                self.assertEqual(name.split(stub)[0], f'20261002_{ix.name}_')
                self.assertFalse(downstream_incompatible(well, pos))

    def test_site_one_is_not_confused_with_site_ten(self):
        names = ['20261002_P_A06_s1_phs.tif', '20261002_P_A06_s10_phs.tif']
        self.assertEqual([n for n in names if 'A06_s1' + '_' in n], [names[0]])

    def test_incompatible_names_are_flagged(self):
        self.assertFalse(downstream_incompatible('E10', 's5'))
        self.assertFalse(downstream_incompatible('H12', 's99'))
        self.assertTrue(downstream_incompatible('I13', 's1'))     # 384-well plate
        self.assertTrue(downstream_incompatible('A01', 's100'))
        self.assertTrue(downstream_incompatible('A01', 'sc02sr05'))


class TestTimeFolders(TmpDirTestCase):

    def make(self, base: Path, timepoints, prefix='Timepoint_', with_t=False,
             sites=((2, 5), (7, 6))):
        for t in timepoints:
            for sc, sr in sites:
                touch(base / f'{prefix}{t}' /
                      new_name(10, 5, sc, sr, 1, t if with_t else None))

    def test_folders_sorted_numerically(self):
        self.make(self.root, timepoints=range(1, 13))
        ix = index_time_folders(self.root)
        self.assertEqual(ix.timepoints, list(range(1, 13)))
        files = ix.files('E10', 's1', 'w01')
        self.assertEqual([f.parent.name for f in files],
                         [f'Timepoint_{t}' for t in range(1, 13)])

    def test_various_folder_prefixes(self):
        for prefix in ['TimePoint_', 'Timepoint', 'T', 'time-', 'Time Point ']:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as d:
                self.make(Path(d), timepoints=[1, 2, 10], prefix=prefix)
                self.assertEqual(index_time_folders(Path(d)).timepoints, [1, 2, 10])

    def test_zero_padded_folder_numbers(self):
        for t in (1, 2, 10):
            touch(self.root / f'T{t:03d}' / new_name(1, 1, 1, 1, 1))
        self.assertEqual(index_time_folders(self.root).timepoints, [1, 2, 10])

    def test_folder_number_overrides_t_token(self):
        # a _t token in the file name is ignored in favour of the folder
        touch(self.root / 'TP_5' / new_name(1, 1, 1, 1, 1, t=1))
        self.assertEqual(index_time_folders(self.root).timepoints, [5])

    def test_time_folders_one_level_down(self):
        self.make(self.root / 'plate', timepoints=[1, 2, 3])
        self.assertEqual(index_time_folders(self.root).timepoints, [1, 2, 3])

    def test_stray_numbered_folder_is_ignored(self):
        self.make(self.root, timepoints=range(1, 6))
        touch(self.root / 'Plate2' / new_name(1, 1, 1, 1, 1))
        ix = index_time_folders(self.root)
        self.assertEqual(ix.timepoints, [1, 2, 3, 4, 5])
        self.assertEqual(ix.wells, ['E10'])

    def test_duplicate_timepoint_folders_is_an_error(self):
        touch(self.root / 'T1' / new_name(1, 1, 1, 1, 1))
        touch(self.root / 'T01' / new_name(1, 1, 1, 1, 1))
        with self.assertRaises(ValueError):
            index_time_folders(self.root)

    def test_legacy_names_accepted_as_fallback(self):
        for t in (1, 2):
            touch(self.root / f'T{t}' / f'Plate_B03_s1_w1{t}ABCDEF.tif')
        ix = index_time_folders(self.root)
        self.assertEqual(list(ix.stacks), [('B03', 's1', 'w1')])

    def test_find_time_dirs(self):
        self.make(self.root, timepoints=[3, 1, 2])
        dirs = find_time_dirs(self.root)
        self.assertEqual(sorted(dirs), [1, 2, 3])
        self.assertEqual(dirs[2].name, 'Timepoint_2')
        self.assertEqual(find_time_dirs(self.root, prefix='Other'), {})

    def test_no_time_folders(self):
        touch(self.root / new_name(1, 1, 1, 1, 1, 1))
        self.assertIsNone(index_time_folders(self.root))


class TestLegacy(TmpDirTestCase):

    def make(self, timepoints, wells=('A10', 'B03'), sites=('s1', 's2'),
             wavelengths=('w1', 'w2')):
        rng = random.Random(1)
        for t in timepoints:
            for well in wells:
                for site in sites:
                    for w in wavelengths:
                        guid = '%08X-9FCF-40D3-937C-2D51B516160F' % rng.getrandbits(32)
                        d = self.root / f'TimePoint_{t}'
                        touch(d / f'20250612_{well}_{site}_{w}{guid}.tif')
                        touch(d / f'20250612_{well}_{site}_{w}_thumb{guid}.tif')

    def test_legacy_layout(self):
        self.make(range(1, 12))
        ix = index_legacy(self.root)
        self.assertEqual(ix.name, '20250612')
        self.assertEqual(ix.wells, ['A10', 'B03'])
        self.assertEqual(ix.positions, ['s1', 's2'])
        self.assertEqual(ix.wavelengths, ['w1', 'w2'])
        self.assertEqual(ix.timepoints, list(range(1, 12)))
        files = ix.files('A10', 's2', 'w2')
        self.assertEqual([f.parent.name for f in files],
                         [f'TimePoint_{t}' for t in range(1, 12)])
        self.assertTrue(all('_w2' in f.name and 'thumb' not in f.name for f in files))

    def test_layouts_do_not_cross_match(self):
        self.make([1, 2])
        self.assertIsNone(build_index(self.root, 'single_folder'))

    def test_unknown_layout(self):
        with self.assertRaises(ValueError):
            build_index(self.root, 'nope')


SINGLE_FOLDER_DATA = Path(os.environ.get(
    'IXN_SINGLE_FOLDER_DATA',
    '/Volumes/SharedHITSX/cdb-Joglekar-Lab-GL/Anish_Virdi/CycB_dynamics/ixn/20261002'))
LEGACY_DATA = Path(os.environ.get(
    'IXN_LEGACY_DATA',
    '/Volumes/SharedHITSX/cdb-Joglekar-Lab-GL/Anish_Virdi/CycB_dynamics/ixn/'
    '20250612-cycb-noc-gsk/20250612/2025-06-13/20448'))
TIME_FOLDERS_DATA = Path(os.environ.get(
    'IXN_TIME_FOLDERS_DATA',
    '/Volumes/SharedHITSX/cdb-Joglekar-Lab-GL/Anish_Virdi/CycB_dynamics/ixn/20261005'))


class TestRealData(unittest.TestCase):

    def assert_sites_match_stage_labels(self, ix):
        '''s<N> inferred from the file names == 'Site N' in each stack's
        stage-label metadata, e.g. 'E10 : Site 5'.'''
        import tifffile
        for (well, pos, w), frames in ix.stacks.items():
            with tifffile.TiffFile(frames[0].path) as tf:
                label = tf.metaseries_metadata['PlaneInfo']['stage-label']
            self.assertEqual(label, f'{well} : Site {pos[1:]}', frames[0].path.name)

    @unittest.skipUnless(SINGLE_FOLDER_DATA.is_dir(), f'{SINGLE_FOLDER_DATA} not available')
    def test_20261002_single_folder(self):
        ix = build_index(SINGLE_FOLDER_DATA, 'single_folder')
        self.assertIsNotNone(ix)
        # every stack runs over consecutive timepoints with no gaps or repeats
        for key, frames in ix.stacks.items():
            self.assertEqual([f.timepoint for f in frames], ix.timepoints, key)
            for f in frames:
                self.assertIn(f'_t{f.timepoint:03d}_', f.path.name)
        if SINGLE_FOLDER_DATA.name == '20261002':
            self.assertEqual(ix.name, PLATE)
            self.assertEqual(len(ix.stacks), 81)
            self.assertEqual(ix.timepoints, list(range(1, 134)))
            self.assertEqual(ix.wavelengths, ['w01'])
            self.assertEqual(len(ix.positions), 9)
            self.assertEqual(ix.wells, ['A10', 'A11', 'B10', 'C10', 'D10',
                                        'E10', 'F10', 'G10', 'H10'])
            self.assertEqual(ix.positions, [f's{n}' for n in range(1, 10)])
        self.assert_sites_match_stage_labels(ix)

    @unittest.skipUnless(LEGACY_DATA.is_dir(), f'{LEGACY_DATA} not available')
    def test_legacy_matches_original_glob(self):
        '''The legacy indexer finds the same files, in the same order, as the
        original recursive glob + TimePoint sort.'''
        ix = build_index(LEGACY_DATA, 'legacy')
        self.assertIsNotNone(ix)
        well, pos, w = sorted(ix.stacks)[0]
        stub = '_'.join([ix.name, well, pos, w])
        original = sorted(
            (f for f in LEGACY_DATA.glob('**/' + stub + '*')
             if f.suffix.casefold() == '.tif' and 'thumb' not in f.name.casefold()),
            key=lambda x: int(x.parent.name.split('_')[-1]))
        self.assertEqual(ix.files(well, pos, w), original)

    @unittest.skipUnless(TIME_FOLDERS_DATA.is_dir(), f'{TIME_FOLDERS_DATA} not available')
    def test_time_folders(self):
        ix = build_index(TIME_FOLDERS_DATA, 'time_folders')
        self.assertIsNotNone(ix)
        for key, frames in ix.stacks.items():
            self.assertEqual([f.timepoint for f in frames], ix.timepoints, key)
            # one folder per frame, in increasing timepoint order
            self.assertEqual(len({f.path.parent for f in frames}), len(frames), key)
        if TIME_FOLDERS_DATA.name == '20261005':
            # RPE1-U2OS-noc/t001 .. t297
            self.assertEqual(ix.name, 'RPE1-U2OS-noc')
            self.assertEqual(len(ix.stacks), 144)
            self.assertEqual(ix.timepoints, list(range(1, 298)))
            self.assertEqual(ix.wavelengths, ['w01', 'w02'])
            self.assertEqual(ix.positions, [f's{n}' for n in range(1, 9)])
            for frames in ix.stacks.values():
                for f in frames:
                    self.assertEqual(f.path.parent.name, f't{f.timepoint:03d}')
                    self.assertIn(f'_t{f.timepoint:03d}_', f.path.name)
        self.assert_sites_match_stage_labels(ix)
        print(f'\n{TIME_FOLDERS_DATA}: {len(ix.stacks)} stacks, wells {ix.wells}, '
              f'positions {ix.positions}, wavelengths {ix.wavelengths}, '
              f'{len(ix.timepoints)} timepoints')


if __name__ == '__main__':
    unittest.main()
