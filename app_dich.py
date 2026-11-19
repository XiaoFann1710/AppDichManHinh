import sys
import time
import mss
import easyocr
import numpy as np
import keyboard
import difflib
import ctypes  # Thư viện gọi API hệ thống của Windows
import google.generativeai as genai
from deep_translator import GoogleTranslator
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QRubberBand
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor


# ---------------------------------------------------------
# LUỒNG 1: XỬ LÝ NHẬN DIỆN VÀ DỊCH CHỮ BẰNG AI GEMINI
# ---------------------------------------------------------
class OCRThread(QThread):
    text_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.paused = False
        self.reader = easyocr.Reader(['ch_sim', 'en'])
        self.region = None

        # Thêm biến này để lưu lại câu thoại cuối cùng đã dịch
        self.last_text = ""

        genai.configure(api_key='')
        self.model = genai.GenerativeModel('gemini-3.7-flash')

    def run(self):
        with mss.mss() as sct:
            while self.running:
                if self.region is not None and not self.paused:
                    try:
                        img = np.array(sct.grab(self.region))
                        text_list = self.reader.readtext(img, detail=0, paragraph=True)
                        current_text = " ".join(text_list).strip()

                        # 1. LỌC BẰNG ĐỘ DÀI
                        if len(current_text) < 5:
                            continue

                        # 2. LỌC BẰNG ĐỘ GIỐNG NHAU
                        similarity = difflib.SequenceMatcher(None, current_text, self.last_text).ratio()

                        if similarity < 0.85:  # Chỉ dịch nếu khác biệt trên 15%
                            self.last_text = current_text

                            prompt = f"""
                            Bạn là một dịch giả game chuyên nghiệp. Hãy dịch đoạn hội thoại sau sang tiếng Việt.
                            Yêu cầu quan trọng:
                            - Văn phong tự nhiên, mượt mà.
                            - Dựa vào nội dung câu nói, hãy tự suy luận mối quan hệ, vai vế giữa các nhân vật để sử dụng đại từ xưng hô tiếng Việt cho chuẩn xác nhất (ví dụ: tôi - cậu, anh - em, ngài - tôi, cô - tôi...).
                            - Giữ nguyên tên riêng tiếng Anh (nếu có).
                            - Tuyệt đối không giải thích hay phân tích, chỉ in ra bản dịch cuối cùng.

                            Văn bản cần dịch: "{current_text}"
                            """

                            response = self.model.generate_content(prompt)
                            translated = response.text.strip()
                            self.text_updated.emit(translated)

                    except Exception as e:
                        print(f"Lỗi AI: {e}")

                time.sleep(2.0)

    def stop(self):
        self.running = False
        self.quit()


# ---------------------------------------------------------
# LUỒNG 2: LẮNG NGHE PHÍM TẮT (F3, F4, F5)
# ---------------------------------------------------------
class HotkeyThread(QThread):
    trigger_snip = pyqtSignal()
    trigger_pause = pyqtSignal()
    trigger_exit = pyqtSignal()

    def run(self):
        keyboard.add_hotkey('f4', lambda: self.trigger_snip.emit())
        keyboard.add_hotkey('f3', lambda: self.trigger_pause.emit())
        keyboard.add_hotkey('f5', lambda: self.trigger_exit.emit())
        keyboard.wait()


# ---------------------------------------------------------
# GIAO DIỆN 1: CÔNG CỤ CẮT MÀN HÌNH
# ---------------------------------------------------------
class SnippingWidget(QWidget):
    on_snipped = pyqtSignal(dict, QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
        self.origin = QPoint()

    def start_snipping(self):
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, self.origin))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.rubberBand.hide()
            rect = QRect(self.origin, event.pos()).normalized()

            region = {
                "top": rect.y(),
                "left": rect.x(),
                "width": rect.width(),
                "height": rect.height()
            }

            self.on_snipped.emit(region, rect)
            self.hide()


# ---------------------------------------------------------
# GIAO DIỆN 2: LỚP PHỦ HIỂN THỊ CHỮ DỊCH
# ---------------------------------------------------------
class OverlayTranslator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # --- BẮT ĐẦU ĐOẠN PHÉP THUẬT ---
        try:
            # Lấy ID của cửa sổ PyQt5 này
            hwnd = int(self.winId())
            # Gọi API Windows để đánh dấu cửa sổ này là "loại trừ khỏi ảnh chụp màn hình" (Mã 0x00000011)
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
        except Exception as e:
            print("Không thể bật chế độ tàng hình:", e)
        # --- KẾT THÚC ĐOẠN PHÉP THUẬT ---

        self.label = QLabel("Đang chờ hội thoại...", self)
        self.label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: bold;
                background-color: rgba(0, 0, 0, 180);
                padding: 10px;
                border-radius: 8px;
                border: 2px solid #55aaff;
            }
        """)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.setLayout(layout)


# ---------------------------------------------------------
# MAIN KHỞI CHẠY
# ---------------------------------------------------------
if __name__ == '__main__':
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

        # Nhờ API tàng hình, ta có thể đặt khung dịch ĐÈ TRỰC TIẾP lên chữ gốc
        overlay.setGeometry(rect.x(), rect.y(), rect.width(), rect.height())

        overlay.label.setText("Đã nhận diện vùng. Đang quét chữ...")
        overlay.show()


    snipper.on_snipped.connect(handle_snipped)
    ocr_thread.text_updated.connect(overlay.label.setText)

    overlay.hide()
    snipper.hide()

    app.aboutToQuit.connect(ocr_thread.stop)
    sys.exit(app.exec_())