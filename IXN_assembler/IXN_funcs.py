
# import re
import os
from pathlib import Path
import tifffile as tiff
import numpy as np
from qtpy import QtWidgets
import napari
import napari.utils.notifications as notifications
from typing import Optional, List, Dict
from dataclasses import dataclass
from IXN_assembler import ui  # type:ignore

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
    

def retrieveMetaData(path: Path):
    # The relevant data is a dictionary within the metadata dictionary called "PlaneInfo"
    metadata = tiff.TiffFile(path).metaseries_metadata['PlaneInfo']

    return metadata

def retrieveIXNInfo(data_path: Path):
    data_dir = Path(data_path)

    timepoints = []
    for dir in os.scandir(data_dir):
        if 'TimePoint' in dir.name:
            timepoints.append(dir.name)

    if not timepoints:
        
        return
    
    else:
        timepoints = sorted(timepoints)

        # Files in the first timepoint directory
        file_list = [f.name for f in os.scandir(data_dir / timepoints[0])
                        if 'thumb' not in f.name.casefold()]

        # Retrieve the date
        img = tiff.TiffFile(data_dir / timepoints[0] / file_list[0])
        date = img.pages[0].tags['DateTime'].value.split(' ')[0]
        imwidth  = img.pages[0].tags['ImageWidth'].value
        imheight = img.pages[0].tags['ImageLength'].value
        # Infer expt. details from the first directory
        wells = []
        positions = []
        wavelengths = []
        for file in file_list:
            splits = file.split('_')
            name = splits[0]
            wells.append(splits[1])
            positions.append(splits[2])
            wavelengths.append(splits[3][0:2])

        wells = sorted(list(set(wells)))
        positions = sorted(list(set(positions)))
        # This stores the 'w*' suffix in file names
        wavelengths = sorted(list(set(wavelengths)))

        # Read channel filter cube for each image
        channel_names = []
        for wavelength in wavelengths:
            templist = [filename for filename in file_list if wavelength in filename][0]
            metadata = retrieveMetaData(data_dir / timepoints[0] / templist)
            channel_names.append(metadata['ImageXpress Micro Filter Cube'])


        # Create the expt. info data class
        IXNInfo = exptInfo(data_dir, name, date,
                        wells, positions,
                        wavelengths, timepoints,
                        imwidth, imheight)
        IXNInfo.channel_names = channel_names
        return IXNInfo



def write_metadata_files(IXN_info):
    """Write per-channel metadata text files to the experiment directory."""
    data_dir = IXN_info.data_dir
    timepoints = IXN_info.timepoints

    file_list = [f.name for f in os.scandir(data_dir / timepoints[0])
                 if 'thumb' not in f.name.casefold()]
    file_list1 = [f.name for f in os.scandir(data_dir / timepoints[1])
                  if 'thumb' not in f.name.casefold()]

    img0 = tiff.TiffFile(data_dir / timepoints[0] / file_list[0])
    img1 = tiff.TiffFile(data_dir / timepoints[1] / file_list1[0])
    time_0 = int(img0.pages[0].tags['DateTime'].value.split(':')[1])
    time_1 = int(img1.pages[0].tags['DateTime'].value.split(':')[1])

    metadata_keys = ['spatial-calibration-x',
                     'camera-binning-x',
                     '_MagNA_', '_MagSetting_',
                     'Exposure Time', '_IllumSetting_',
                     'ImageXpress Micro Filter Cube',
                     'Lumencor Intensity',
                     ]

    for wavelength in IXN_info.wavelengths:
        tempfile = [f for f in file_list if wavelength in f][0]
        metadata = retrieveMetaData(data_dir / timepoints[0] / tempfile)

        metadataname = IXN_info.date + '_' + wavelength + '_metadata.txt'
        txtfile = data_dir / metadataname
        with open(txtfile, 'w') as txt:
            for key in metadata_keys:
                txt.write(key + ':' + str(metadata[key]) + '\n')
            txt.write('Time interval' + ':' + str(time_1 - time_0) + ' min')
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
        #Remove thumbnail files
        allfiles = Path(IXN_widget.expt_info.data_dir
                    / IXN_widget.expt_info.timepoints[0]).glob(name_stub+str(i+1)+'*')
        nonthumbs = [file for file in allfiles if "thumb" not in file.name.casefold()]

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
    completed = 0
    for stub in IXN_widget.positions_to_write:
        for wave_idx, ch_name in ch_selections:
            # Add date prior to the name.
            save_name = IXN_widget.expt_info.date+"_"+stub[:-1]+ch_name+'.tif'
            file_path = save_path / save_name
            if not file_path.exists():
                im_array = np.zeros((len(IXN_widget.expt_info.timepoints),
                                    IXN_widget.expt_info.imwidth,
                                    IXN_widget.expt_info.imheight), dtype='uint16')

                # Create a list of files excluding the thumb files
                allfiles = IXN_widget.expt_info.data_dir.glob('**/'+stub+str(wave_idx+1)+'*')
                nonthumbs = [file for file in allfiles if "thumb" not in file.name.casefold()]
                # Sort the filenames in order of their parent directory time stamp number
                sorted_nonthumbs = sorted(nonthumbs, key=lambda x: int(x.parent.name.split("_")[-1]))
                for k, f in enumerate(sorted_nonthumbs):
                    im_array[k,:,:] = tiff.imread(f)

                tiff.imwrite(file_path, im_array)
                print(f'Written: {save_name}')
            else:
                print(f'Skipped (already exists): {save_name}')

            completed += 1
            IXN_widget.progress_bar.setValue(int(100 * completed / total_ops))
    return