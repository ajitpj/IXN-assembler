
# import re
from pathlib import Path
import tifffile as tiff
import numpy as np
from qtpy import QtWidgets
import napari.utils.notifications as notifications
from typing import Optional
from dataclasses import dataclass, field
from IXN_assembler.file_layouts import LAYOUT_LABELS, StackIndex, build_index

METADATA_KEYS = ['spatial-calibration-x',
                 'camera-binning-x',
                 '_MagNA_', '_MagSetting_',
                 'Exposure Time', '_IllumSetting_',
                 'ImageXpress Micro Filter Cube',
                 'Lumencor Intensity',
                 ]


@dataclass
class exptInfo:
    data_dir: Path
    name: str
    date: str
    wells: list
    positions: list
    wavelengths: list
    timepoints: list
    imwidth:  int = 2048
    imheight: int = 2048
    channel_names: list = field(default_factory=list)
    stacks: Optional[StackIndex] = None
    # 'name_well_pos_w' write-list entry -> (well, position)
    stub_lookup: dict = field(default_factory=dict)


def position_stub(name: str, well: str, position: str) -> str:
    '''Write-list entry for one well/position, e.g. 'pFF1-CycB_A06_s1_w'.'''
    return '_'.join([name, well, position, 'w'])


def retrieveMetaData(path: Path):
    # The relevant data is a dictionary within the metadata dictionary called "PlaneInfo"
    metadata = tiff.TiffFile(path).metaseries_metadata['PlaneInfo']

    return metadata


def acquisition_time(path: Path):
    '''Acquisition timestamp of a single image, as a datetime.

    The TIFF DateTime tag holds the same instant, but only as a string; the
    MetaSeries metadata gives it already parsed.'''
    return retrieveMetaData(path)['acquisition-time-local']


def time_interval(frames: list, max_pairs: int = 5,
                  get_time=acquisition_time) -> Optional[float]:
    '''Median interval, in minutes, between consecutive timepoints.

    frames: (timepoint, path) pairs of a single stack, in timepoint order.
    The same well/position/wavelength has to be followed across timepoints:
    one timepoint scans the whole plate over several minutes, so two images
    from different positions are not acquired at the same time.'''
    times = [(t, get_time(path)) for t, path in frames[:max_pairs + 1]]
    if len(times) < 2:
        return None

    # divide by the timepoint gap so a position missing from one timepoint
    # does not read as a doubled interval
    deltas = [(t1 - t0).total_seconds() / 60 / (i1 - i0)
              for (i0, t0), (i1, t1) in zip(times, times[1:])]
    return float(np.median(deltas))


def retrieveIXNInfo(data_path: Path, layout: str = 'legacy'):
    '''Index the experiment in data_path, stored in the given file layout
    (see file_layouts.LAYOUTS). Returns None if no images are found; raises
    ValueError if the images cannot be grouped into stacks unambiguously.'''
    data_dir = Path(data_path)

    stacks = build_index(data_dir, layout)
    if stacks is None:
        return

    # Retrieve the date and image size from the first image
    img = tiff.TiffFile(stacks.first_file())
    date = img.pages[0].tags['DateTime'].value.split(' ')[0]
    imwidth  = img.pages[0].tags['ImageWidth'].value
    imheight = img.pages[0].tags['ImageLength'].value

    # Read channel filter cube for each wavelength ('w*' suffix in file names)
    channel_names = [
        retrieveMetaData(stacks.first_file(wavelength))
        ['ImageXpress Micro Filter Cube']
        for wavelength in stacks.wavelengths
    ]

    stub_lookup = {position_stub(stacks.name, well, pos): (well, pos)
                   for well, pos, _ in stacks.stacks}

    # Create the expt. info data class
    return exptInfo(data_dir, stacks.name, date,
                    stacks.wells, stacks.positions,
                    stacks.wavelengths, stacks.timepoints,
                    imwidth, imheight,
                    channel_names, stacks, stub_lookup)


def write_metadata_files(IXN_info):
    """Write per-channel metadata text files to the experiment directory."""
    data_dir = IXN_info.data_dir
    timepoints = IXN_info.timepoints

    for wavelength in IXN_info.wavelengths:
        metadata = retrieveMetaData(IXN_info.stacks.first_file(wavelength))
        # follow the first stack recorded at this wavelength
        frames = next(frames for (_, _, w), frames
                      in sorted(IXN_info.stacks.stacks.items())
                      if w == wavelength)
        interval = time_interval(frames)

        metadataname = IXN_info.date + '_' + wavelength + '_metadata.txt'
        txtfile = data_dir / metadataname
        with open(txtfile, 'w') as txt:
            for key in METADATA_KEYS:
                txt.write(key + ':' + str(metadata[key]) + '\n')
            if interval is None:
                txt.write('Time interval:unknown\n')
            else:
                # round first so a 4.02 min nominal interval reads as '4 min'
                txt.write(f'Time interval:{round(interval, 1):g} min\n')
            txt.write(f'Number of timepoints:{len(timepoints)}\n')
        print(f'Metadata file for {txtfile} written!')
        notifications.show_info(f'Metadata file for {txtfile} written!')


def select_dir(IXN_widget):
    '''
    Returns one user selected Path
    '''
    # import retrieveIXNInfo

    dir_path = QtWidgets.QFileDialog.getExistingDirectory()
    if not dir_path:
        return
    IXN_widget.data_dir = Path(dir_path)
    IXN_widget.path_selector_button.setToolTip(dir_path)
    load_dir(IXN_widget)


def selected_layout(IXN_widget) -> str:
    '''File layout picked with the layout checkboxes.'''
    for layout, chkbox in IXN_widget.layout_checkboxes.items():
        if chkbox.isChecked():
            return layout
    return 'legacy'


def reset_selectors(IXN_widget):
    '''Empty the well/position menus, the write list and the channel names
    left over from a previously loaded folder.'''
    for i in (2, 3, 4):
        IXN_widget.__dict__['ch'+str(i)+'_LineEdit'].clear()
        chkbox = IXN_widget.__dict__['ch'+str(i)+'_chkbox']
        chkbox.setText('')
        chkbox.setChecked(False)
        chkbox.setEnabled(False)
    for selector in (IXN_widget.well_selector, IXN_widget.posi_selector):
        selector.blockSignals(True)
        selector.clear()
        selector.blockSignals(False)
    IXN_widget.display_write_list.clear()
    IXN_widget.positions_to_write = []


def layout_changed(IXN_widget, checked: bool):
    '''Re-read the selected folder when the user switches file layout.'''
    if checked and IXN_widget.data_dir is not None:
        load_dir(IXN_widget)


def load_dir(IXN_widget):
    '''Index IXN_widget.data_dir with the selected layout and fill the GUI.'''
    layout = selected_layout(IXN_widget)
    reset_selectors(IXN_widget)
    remove_napari_layers(IXN_widget)

    # retrieve expt info and assign it to the ui
    try:
        IXN_widget.expt_info = retrieveIXNInfo(IXN_widget.data_dir, layout)
    except ValueError as err:
        IXN_widget.expt_info = None
        notifications.show_error(str(err))
        return

    if IXN_widget.expt_info:
        info = IXN_widget.expt_info
        notifications.show_info(
            f'{info.name}: {len(info.wells)} wells, {len(info.positions)} '
            f'positions, {len(info.wavelengths)} wavelengths, '
            f'{len(info.timepoints)} timepoints')
        # retrieve the metadata to read the filters used for each wavelength
        lineedit_dict = {2 : IXN_widget.ch2_LineEdit,
                         3 : IXN_widget.ch3_LineEdit,
                         4 : IXN_widget.ch4_LineEdit}
        # first channel is always phase; start with the second
        IXN_widget.ch1_chkbox.setEnabled(True)
        for i, channel_name in enumerate(IXN_widget.expt_info.channel_names[1::]):
            lineedit_dict[i+2].setText(channel_name)
            IXN_widget.__dict__['ch'+str(i+2)+'_chkbox'].setText(channel_name)
            IXN_widget.__dict__['ch'+str(i+2)+'_chkbox'].setEnabled(True)

        for well in IXN_widget.expt_info.wells:
            IXN_widget.well_selector.addItem(well)
        
        for position in IXN_widget.expt_info.positions:
            IXN_widget.posi_selector.addItem(position)
    else:
        notifications.show_error(
            f'No images found for the "{LAYOUT_LABELS[layout]}" layout!')
        return


def remove_napari_layers(IXN_widget):
    # Remove previous layers
    num_layers = len(IXN_widget.viewer.layers)
    if num_layers>0:
        for i in np.arange(num_layers):
            IXN_widget.viewer.layers.remove(IXN_widget.viewer.layers[-1])
    return

def loadPositiongivenWell(IXN_widget):
    if not IXN_widget.expt_info:
        return
    well = IXN_widget.well_selector.currentText()
    pos  = IXN_widget.posi_selector.currentText()

    name_stub = position_stub(IXN_widget.expt_info.name, well, pos)
    IXN_widget.expt_info.current_name_stub = name_stub
    remove_napari_layers(IXN_widget) # remove old layers
    
    IXN_widget.current_names = [] # Used for retrieving metadata
    for wavelength in IXN_widget.expt_info.wavelengths:
        # first timepoint of this position, if it was imaged at all
        files = IXN_widget.expt_info.stacks.files(well, pos, wavelength)[:1]

        for f in files:
            IXN_widget.viewer.add_image(tiff.imread(f),
                            name = name_stub+wavelength[1:],
                            colormap='gray', opacity=0)
            IXN_widget.current_names.append(f)
           # Disable visibility of w1 to 1
            IXN_widget.viewer.layers[0].opacity=1
    return

def add_to_writelist(IXN_widget):
    if not IXN_widget.expt_info:
        return

    IXN_widget.display_write_list.appendPlainText(IXN_widget.expt_info.current_name_stub)
    IXN_widget.positions_to_write = [
        p for p in IXN_widget.display_write_list.toPlainText().split("\n") if p
    ]
    return


def set_progress(IXN_widget, fraction: float):
    '''Update the progress bar and let Qt repaint it.

    The write loop runs on the GUI thread, so without processEvents the bar
    (and the rest of the window) stays frozen until the last stack is done.'''
    IXN_widget.progress_bar.setValue(int(100 * fraction))
    QtWidgets.QApplication.processEvents()


def write_stack(files: list, file_path: Path, progress=None):
    '''Assemble `files` into one multipage TIFF, one frame at a time.

    Frames are streamed straight to disk rather than collected into a single
    array first: a 460-timepoint 2048x2048 uint16 stack is ~3.9 GB in memory.
    The stack is built under a temporary name and moved into place only once
    it is complete, so an interrupted write cannot leave a truncated file
    behind for a later run to skip as already written.'''
    partial = file_path.with_name(file_path.name + '.part')
    # A classic TIFF cannot address past 4 GB (2**32 bytes). Only fall back to
    # BigTIFF once a stack would actually overflow it: a 460-timepoint
    # 2048x2048 run lands at ~3.86 GB and stays a plain TIFF, as before.
    est_bytes = sum(f.stat().st_size for f in files)
    try:
        with tiff.TiffWriter(partial, bigtiff=est_bytes > 4.0e9) as writer:
            for k, f in enumerate(files):
                # contiguous=True appends to the running series, so the result
                # reads back as a single (t, y, x) stack
                writer.write(tiff.imread(f), contiguous=True)
                if progress:
                    progress((k + 1) / len(files))
        partial.replace(file_path)
    finally:
        if partial.exists():
            partial.unlink()


def write_all_stacks(IXN_widget):
    write_metadata_files(IXN_widget.expt_info)
    save_path = IXN_widget.expt_info.data_dir

    # This dictionary will save the files for each wavelength
    # ch_names = [IXN_widget.ch1_LineEdit.text(),
    #             IXN_widget.ch2_LineEdit.text(),
    #             IXN_widget.ch3_LineEdit.text(),
    #             IXN_widget.ch4_LineEdit.text(),
    #             ]
    
    # Added 20241224: create flags for user selected channels
    # Build list of (wavelength, channel_name) for checked channels only;
    # checkbox i is labelled with the channel of the i-th wavelength.
    ch_checkboxes = [IXN_widget.ch1_chkbox, IXN_widget.ch2_chkbox,
                     IXN_widget.ch3_chkbox, IXN_widget.ch4_chkbox]
    ch_selections = [
        (IXN_widget.expt_info.wavelengths[i], chkbox.text())
        for i, chkbox in enumerate(ch_checkboxes)
        if chkbox.isChecked() and i < len(IXN_widget.expt_info.wavelengths)
    ]

    total_ops = len(IXN_widget.positions_to_write) * len(ch_selections)
    if not total_ops:
        notifications.show_error('Nothing to write: select positions and channels.')
        return

    # processEvents below keeps the GUI live, which also lets the user click
    # 'Write all' again mid-run; disable it until this run is finished.
    IXN_widget.writeall_button.setEnabled(False)
    completed = 0
    set_progress(IXN_widget, 0)
    try:
        for stub in IXN_widget.positions_to_write:
            # the write list is editable, so it may name a position that
            # does not exist in this experiment
            well, pos = IXN_widget.expt_info.stub_lookup.get(stub, (None, None))
            for wavelength, ch_name in ch_selections:
                # Add date prior to the name.
                save_name = IXN_widget.expt_info.date+"_"+stub[:-1]+ch_name+'.tif'
                file_path = save_path / save_name
                if not file_path.exists():
                    # Files of this stack, thumbnails excluded, in timepoint order
                    sorted_nonthumbs = IXN_widget.expt_info.stacks.files(
                        well, pos, wavelength)
                    if not sorted_nonthumbs:
                        notifications.show_error(f'No images found for {save_name}.')
                        print(f'Skipped (no images found): {save_name}')
                        completed += 1
                        set_progress(IXN_widget, completed / total_ops)
                        continue

                    if len(sorted_nonthumbs) != len(IXN_widget.expt_info.timepoints):
                        notifications.show_warning(
                            f'{save_name}: found {len(sorted_nonthumbs)} images for '
                            f'{len(IXN_widget.expt_info.timepoints)} timepoints.')

                    write_stack(sorted_nonthumbs, file_path,
                                progress=lambda frac, done=completed:
                                set_progress(IXN_widget, (done + frac) / total_ops))
                    print(f'Written: {save_name}')
                else:
                    print(f'Skipped (already exists): {save_name}')

                completed += 1
                set_progress(IXN_widget, completed / total_ops)
    finally:
        IXN_widget.writeall_button.setEnabled(True)
    return