# coding: utf-8
from PyQt6.QtCore import QObject, pyqtSignal


class SignalBus(QObject):
    """ Signal bus """

    switchToSampleCard = pyqtSignal(str, int)
    supportSignal = pyqtSignal()


signalBus = SignalBus()