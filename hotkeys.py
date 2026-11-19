import keyboard
from PyQt5.QtCore import QThread, pyqtSignal
import config

class HotkeyThread(QThread):
    trigger_snip = pyqtSignal()
    trigger_pause = pyqtSignal()
    trigger_exit = pyqtSignal()

    def run(self):
        keyboard.add_hotkey(config.HOTKEY_SNIP, lambda: self.trigger_snip.emit())
        keyboard.add_hotkey(config.HOTKEY_PAUSE, lambda: self.trigger_pause.emit())
        keyboard.add_hotkey(config.HOTKEY_EXIT, lambda: self.trigger_exit.emit())
        keyboard.wait()