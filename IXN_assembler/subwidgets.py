from __future__ import annotations
from qtpy import QtWidgets


def create_expt_selector_widgets() -> dict[str,  QtWidgets.QWidget]:
    '''
    Creates Display and Inference Widgets 
    ------------------------------
    RETURNS:
        widgets: dict
            - inference_button: QtWidgets.QPushButton
            - display_button: QtWidgets.QPushButton
            - pbar: QtWidgets.QProgressBar
    '''

    path_selector_button = QtWidgets.QPushButton()
    path_selector_button.setText('IXN data folder')
    path_selector_button.setToolTip(
        'Select folder containig IXN data'
    )

    widgets = {'path_selector_button' :  path_selector_button}

    return widgets

def create_comboBox_widgets() -> dict[str, QtWidgets.QWidget]:
    '''Creates the two comboboxes for well and position selection'''
    well_selector = QtWidgets.QComboBox()
    well_selector.label = 'Well'
    widgets = {'well_selector' : ("Well", well_selector)}
    posi_selector = QtWidgets.QComboBox()
    widgets['posi_selector'] = ("Position", posi_selector)
    
    add_wellpos_button = QtWidgets.QPushButton()
    add_wellpos_button.setText('Add to write list')
    add_wellpos_button.setToolTip("Select well+position for writing")

    display_write_list = QtWidgets.QTextEdit()
    display_write_list.setToolTip("Positions to be written")

    widgets['add_wellpos_button'] = ("", add_wellpos_button)
    widgets['display_write_list'] = ("To write", display_write_list)

    writeall_button = QtWidgets.QPushButton()
    writeall_button.setText('Write all')
    writeall_button.setToolTip("Write all selected positions")
    widgets['writeall_button'] = ("", writeall_button)

    return widgets

def create_channel_lineEdits_widgets() -> dict[str, QtWidgets.QWidget]:
    '''Creates TextEdit boxes for the four channels '''
    ch1_LineEdit = QtWidgets.QLineEdit('phs')
    widgets = {'ch1_LineEdit' : ("Ch1", ch1_LineEdit)}

    ch2_LineEdit = QtWidgets.QLineEdit()
    ch3_LineEdit = QtWidgets.QLineEdit()
    ch4_LineEdit = QtWidgets.QLineEdit()

    widgets['ch2_LineEdit'] = ("Ch2", ch2_LineEdit)
    widgets['ch3_LineEdit'] = ("Ch3", ch3_LineEdit)
    widgets['ch4_LineEdit'] = ("Ch4", ch4_LineEdit)
    
    return widgets

def create_progressbar_widget() ->dict[str, QtWidgets.QWidget]:
    progress_bar = QtWidgets.QProgressBar()
    progress_bar.setMaximum(100)
    progress_bar.setMinimum(0)
    progress_bar.setValue(0)
    progress_bar.label = "Writing..."
    widgets = {"progress_bar":  progress_bar}

    return widgets
# def create_config_widgets() -> dict[str, tuple[str, QtWidgets.QWidget]]:
#     '''
#     Creates Configuration Widgets 
#     ------------------------------
#     RETURNS:
#         widgets: dict
#             - thresholder: QtWidgets.QDoubleSpinBox
#             - confluency_est: QtWidgets.QSpinBox
#             - set_configs: QtWidgets.QPushButton
#     '''

#     thresholder = QtWidgets.QDoubleSpinBox()
#     thresholder.setRange(0, 100)
#     thresholder.setValue(0.5)
#     thresholder.setStepType(QtWidgets.QAbstractSpinBox.AdaptiveDecimalStepType)
#     thresholder.setToolTip(
#         'Set Confidence Hyperparameter'
#     )
#     thresholder.setWrapping(True)
#     widgets = {'thresholder': ('Confidence Threshold', thresholder)}

#     confluency_est = QtWidgets.QSpinBox()
#     confluency_est.setRange(100, 2000)
#     confluency_est.setValue(500)
#     confluency_est.setStepType(QtWidgets.QAbstractSpinBox.AdaptiveDecimalStepType)
#     confluency_est.setToolTip(
#         'Estimate the number of cells in a frame'
#     )

#     widgets['confluency_est'] = ('Number of Cells (Approx.)', confluency_est)

#     set_configs = QtWidgets.QPushButton('Push')
#     set_configs.setToolTip(
#         'Set Configurations'
#     )

#     widgets['set_configs'] = ('Set Configurations', set_configs)


#     return widgets 



    



