# IXN-assembler
A napari plug-in for creating tiff stacks from MetaExpress IXN image data

#Usage
1. Under "File organization", tick the layout the data was saved in (see below).
2. Navigate to the experiment folder using the "IXN data folder" button.
3. The GUI will populate the well and position drop-down menus, infer channel names from the metadata, and write text files in the selected folder containing relevant metadata for each channel. You may change channel names from the edit box - especially for the "Texas Red" channel to something more suitable (mCherry or Cy3).
4. The GUI will show the first time point once a specific well and position are selected from the drop-down menus.
5. Add each desired position to the list to write image stacks. Duplicates are fine; these will be written only once (files are not over-written).
6. Once done, hit the "Write all" button. 

Ticking a different layout re-reads the selected folder.

#File organization
- **Legacy**: select the folder containing the `TimePoint_*` folders. Files are named `<name>_<well>_<site>_w<N><GUID>.tif`.
- **Organized by time**: one folder per timepoint, named text followed by the timepoint number (e.g. `t007`, `Timepoint_7`), directly in the selected folder or one level below it. Files are named `<name>_c<col>_r<row>_sc<site col>_sr<site row>_w<N>[_z<N>].tif`; the timepoint is taken from the folder name.
- **Single-folder storage**: every image in one folder, which may be the selected folder or up to two levels below it. Files are named `<name>_c<col>_r<row>_sc<site col>_sr<site row>_w<N>_t<N>_z<N>.tif`.

In the new naming scheme `c10_r05` is well E10 and the position is shown as e.g. `sc02sr05`. If more than one z-plane is present, each plane becomes its own stack (`sc02sr05z02`).

#Tests
From the repository root, with the img-env environment:

    python -m unittest discover -s tests -v

The parsing tests build trees of empty placeholder files, so they need no image data. `TestRealData` also checks the 20261002 (single-folder), 20261005 (organized-by-time) and 20250612 (legacy) experiments on the lab share when it is mounted; set `IXN_SINGLE_FOLDER_DATA` / `IXN_TIME_FOLDERS_DATA` / `IXN_LEGACY_DATA` to validate other folders.
