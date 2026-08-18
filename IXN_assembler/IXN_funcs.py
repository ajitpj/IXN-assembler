
# import re
import os
from pathlib import Path
import tifffile as tiff
import numpy as np
from qtpy import QtWidgets
import napari.utils.notifications as notifications
from typing import Optional
from dataclasses import dataclass, field

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


def timepoint_index(timepoint_name: str) -> int:
    '''TimePoint_10 -> 10. Timepoints must be ordered numerically; sorting the
    directory names as strings puts TimePoint_10 right after TimePoint_1.'''
    return int(timepoint_name.split('_')[-1])


def list_image_files(directory: Path, pattern: str = '*') -> list:
    '''Sorted list of IXN image files in a directory, thumbnails excluded.'''
    return sorted(f for f in Path(directory).glob(pattern)
                  if f.suffix.casefold() == '.tif'
                  and 'thumb' not in f.name.casefold())


def retrieveMetaData(path: Path):
    # The relevant data is a dictionary within the metadata dictionary called "PlaneInfo"
    metadata = tiff.TiffFile(path).metaseries_metadata['PlaneInfo']

    return metadata


def acquisition_time(path: Path):
    '''Acquisition timestamp of a single image, as a datetime.

    The TIFF DateTime tag holds the same instant, but only as a string; the
    MetaSeries metadata gives it already parsed.'''
    return retrieveMetaData(path)['acquisition-time-local']


def time_interval(data_dir: Path, timepoints: list, wavelength: str,
                  max_pairs: int = 5) -> Optional[float]:
    '''Median interval, in minutes, between consecutive timepoints.

    The same well/position/wavelength has to be followed across timepoints:
    one timepoint scans the whole plate over several minutes, so two images
    from different positions are not acquired at the same time.'''
    if len(timepoints) < 2:
        return None

    first = [f for f in list_image_files(data_dir / timepoints[0])
             if f'_{wavelength}' in f.name]
    if not first:
        return None

    # 'pFF1-CycB_A06_s1_w1' - the part of the name shared across timepoints.
    # The rest is a per-image GUID, so the files have to be matched by prefix.
    name = first[0].name
    stub = name[:name.index(f'_{wavelength}') + len(wavelength) + 1]

    times = []
    for timepoint in timepoints[:max_pairs + 1]:
        matches = list_image_files(data_dir / timepoint, stub + '*')
        if matches:
            times.append((timepoint_index(timepoint), acquisition_time(matches[0])))

    if len(times) < 2:
        return None

    # divide by the timepoint gap so a position missing from one timepoint
    # does not read as a doubled interval
    deltas = [(t1 - t0).total_seconds() / 60 / (i1 - i0)
              for (i0, t0), (i1, t1) in zip(times, times[1:])]
    return float(np.median(deltas))


def retrieveIXNInfo(data_path: Path):
    data_dir = Path(data_path)

    timepoints = [dir.name for dir in os.scandir(data_dir)
                  if 'TimePoint' in dir.name]

    if not timepoints:
        return

    timepoints = sorted(timepoints, key=timepoint_index)

    # Files in the first timepoint directory
    file_list = list_image_files(data_dir / timepoints[0])

    # Retrieve the date
    img = tiff.TiffFile(file_list[0])
    date = img.pages[0].tags['DateTime'].value.split(' ')[0]
    imwidth  = img.pages[0].tags['ImageWidth'].value
    imheight = img.pages[0].tags['ImageLength'].value
    # Infer expt. details from the first directory
    wells = []
    positions = []
    wavelengths = []
    for file in file_list:
        splits = file.name.split('_')
        name = splits[0]
        wells.append(splits[1])
        positions.append(splits[2])
        wavelengths.append(splits[3][0:2])

    wells = sorted(set(wells))
    positions = sorted(set(positions))
    # This stores the 'w*' suffix in file names
    wavelengths = sorted(set(wavelengths))

    # Read channel filter cube for each image
    channel_names = [
        retrieveMetaData([f for f in file_list if f'_{wavelength}' in f.name][0])
        ['ImageXpress Micro Filter Cube']
        for wavelength in wavelengths
    ]

    # Create the expt. info data class
    return exptInfo(data_dir, name, date,
                    wells, positions,
                    wavelengths, timepoints,
                    imwidth, imheight,
                    channel_names)


def write_metadata_files(IXN_info):
    """Write per-channel metadata text files to the experiment directory."""
    data_dir = IXN_info.data_dir
    timepoints = IXN_info.timepoints

    file_list = list_image_files(data_dir / timepoints[0])

    for wavelength in IXN_info.wavelengths:
        tempfile = [f for f in file_list if f'_{wavelength}' in f.name][0]
        metadata = retrieveMetaData(tempfile)
        interval = time_interval(data_dir, timepoints, wavelength)

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
    IXN_widget.path_selector_button.setToolTip(dir_path)

    # retrieve expt info and assign it to the ui
    IXN_widget.expt_info = retrieveIXNInfo(Path(dir_path))

    if IXN_widget.expt_info:
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
        notifications.show_error(f'Not an IXN datafolder!')
        return


def remove_napari_layers(IXN_widget):
    # Remove previous layers
    num_layers = len(IXN_widget.viewer.layers)
    if num_layers>0:
        for i in np.arange(num_layers):
            IXN_widget.viewer.layers.remove(IXN_widget.viewer.layers[-1])
    return

def loadPositiongivenWell(IXN_widget):
    well = IXN_widget.well_selector.currentText()
    pos  = IXN_widget.posi_selector.currentText()

    name_stub = "_".join([IXN_widget.expt_info.name, well, pos, 'w'])
    IXN_widget.expt_info.current_name_stub = name_stub
    remove_napari_layers(IXN_widget) # remove old layers
    
    IXN_widget.current_names = [] # Used for retrieving metadata
    for i in np.arange(len(IXN_widget.expt_info.wavelengths)):
        nonthumbs = list_image_files(
            IXN_widget.expt_info.data_dir / IXN_widget.expt_info.timepoints[0],
            name_stub + str(i+1) + '*')

        for f in nonthumbs:
            IXN_widget.viewer.add_image(tiff.imread(f),
                            name = name_stub+str(i+1),
                            colormap='gray', opacity=0)
            IXN_widget.current_names.append(f)
           # Disable visibility of w1 to 1
            IXN_widget.viewer.layers[0].opacity=1
    return

def add_to_writelist(IXN_widget):

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
    # Build list of (wavelength_index, channel_name) for checked channels only,
    # preserving the correct 1-based wavelength index (w1=0, w2=1, ...) for each.
    ch_checkboxes = [IXN_widget.ch1_chkbox, IXN_widget.ch2_chkbox,
                     IXN_widget.ch3_chkbox, IXN_widget.ch4_chkbox]
    ch_selections = [
        (i, chkbox.text())
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
            for wave_idx, ch_name in ch_selections:
                # Add date prior to the name.
                save_name = IXN_widget.expt_info.date+"_"+stub[:-1]+ch_name+'.tif'
                file_path = save_path / save_name
                if not file_path.exists():
                    # Create a list of files excluding the thumb files, sorted in
                    # order of their parent directory time stamp number
                    nonthumbs = list_image_files(IXN_widget.expt_info.data_dir,
                                                 '**/'+stub+str(wave_idx+1)+'*')
                    sorted_nonthumbs = sorted(nonthumbs,
                                              key=lambda x: timepoint_index(x.parent.name))
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