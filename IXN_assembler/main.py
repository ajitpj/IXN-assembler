from __future__ import annotations
import logging

import napari
import IXN_assembler.ui as ui  # type:ignore
import numpy as np
import tifffile as tiff
import re
import os
# os.environ["QT_API"] = "pyqt6"
from qtpy import QtWidgets
from IXN_assembler import IXN_funcs

def create_IXN_widget() -> ui.IXNWidget:
    "Creates instance of ui.IXNwidget and sets callbacks"

    IXN_widget = ui.IXNWidget(
        napari_viewer=napari.current_viewer()
    )

    IXN_widget.path_selector_button.clicked.connect(lambda: IXN_funcs.select_dir(IXN_widget))
    IXN_widget.posi_selector.currentIndexChanged.connect(lambda: IXN_funcs.loadPositiongivenWell(IXN_widget))
    IXN_widget.well_selector.currentIndexChanged.connect(lambda: IXN_funcs.loadPositiongivenWell(IXN_widget))
    IXN_widget.add_wellpos_button.clicked.connect(lambda: IXN_funcs.add_to_writelist(IXN_widget))
    IXN_widget.writeall_button.clicked.connect(lambda: IXN_funcs.write_all_stacks(IXN_widget))

    return IXN_widget

