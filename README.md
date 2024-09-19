# IXN-assembler
A napari plug-in for creating tiff stacks from MetaExpress IXN image data

#Usage
1. Navigate to the folder containing the ImageExplorerNano data repository containing the "TimePoint_*" folders using the top button.
2. The GUI will populate the well and position drop-down menus, infer channel names from the metadata, and write text files in the selected folder containing relevant metadata for each channel. You may change channel names from the edit box - especially for the "Texas Red" channel to something more suitable (mCherry or Cy3).
3. The GUI will show the first time point once a specific well and position are selected from the drop-down menus.
4. Add each desired position to the list to write image stacks. Duplicates are fine; these will be written only once (files are not over-written).
5. Once done, hit the "Write all" button. 
