import sys
from PyQt5.QtWidgets import QApplication
from UI_widgets import SnippingWidget, OverlayTranslator
from OCR_engine import OCRThread
from hotkeys import HotkeyThread

def main():
    app = QApplication(sys.argv)

    overlay = OverlayTranslator()
    snipper = SnippingWidget()

    ocr_thread = OCRThread()
    ocr_thread.start()

    hotkey_thread = HotkeyThread()
    hotkey_thread.start()

    hotkey_thread.trigger_snip.connect(snipper.start_snipping)

    def toggle_pause():
        ocr_thread.paused = not ocr_thread.paused
        if ocr_thread.paused:
            overlay.hide()
        elif ocr_thread.region is not None:
            overlay.label.setText("Đã tiếp tục dịch...")
            overlay.show()

    hotkey_thread.trigger_pause.connect(toggle_pause)
    hotkey_thread.trigger_exit.connect(app.quit)

    def handle_snipped(region, rect):
        ocr_thread.region = region
        ocr_thread.paused = False
        overlay.setGeometry(rect.x(), rect.y(), rect.width(), rect.height())
        overlay.label.setText("Đã nhận diện vùng. Đang quét chữ...")
        overlay.show()

    snipper.on_snipped.connect(handle_snipped)
    ocr_thread.text_updated.connect(overlay.label.setText)

    overlay.hide()
    snipper.hide()

    app.aboutToQuit.connect(ocr_thread.stop)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()