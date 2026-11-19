import time
import mss
import numpy as np
import difflib
import asyncio
import cv2
import json
import os
from openai import OpenAI
from PyQt5.QtCore import QThread, pyqtSignal
import config

from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
from winsdk.windows.security.cryptography import CryptographicBuffer


class OCRThread(QThread):
    text_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.paused = False
        self.region = None
        self.last_text = ""

        # --- KHỞI TẠO DATABASE ---
        self.db_path = "local_db.json"
        self.local_db = self.load_db()
        # -------------------------

        # --- KHỞI TẠO GROK API ---
        self.client = OpenAI(
            api_key=config.GROK_API_KEY,
            base_url="https://api.x.ai/v1",
        )
        # -------------------------

        self.ocr_engine = OcrEngine.try_create_from_user_profile_languages()

    # Hàm đọc dữ liệu từ file JSON lên RAM
    def load_db(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Lỗi đọc DB: {e}")
                return {}
        return {}

    # Hàm ghi dữ liệu mới xuống file JSON
    def save_db(self):
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.local_db, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Lỗi lưu DB: {e}")

    def run(self):
        asyncio.run(self.async_run())

    async def async_run(self):
        with mss.mss() as sct:
            while self.running:
                if self.region is not None and not self.paused:
                    try:
                        # 1. Chụp ảnh màn hình
                        raw_img = np.array(sct.grab(self.region))

                        # 2. BỘ LỌC OPENCV
                        gray = cv2.cvtColor(raw_img, cv2.COLOR_BGRA2GRAY)
                        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        processed_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGRA)
                        height, width, _ = processed_img.shape

                        # 3. Đưa vào Windows OCR
                        buffer = CryptographicBuffer.create_from_byte_array(processed_img.tobytes())
                        bitmap = SoftwareBitmap.create_copy_from_buffer(
                            buffer, BitmapPixelFormat.BGRA8, width, height, BitmapAlphaMode.PREMULTIPLIED
                        )
                        result = await self.ocr_engine.recognize_async(bitmap)
                        current_text = result.text.strip()

                        # 4. Lọc chữ rác
                        if len(current_text) < config.MIN_TEXT_LENGTH:
                            time.sleep(config.SCAN_INTERVAL_SECONDS)
                            continue

                        # 5. Xử lý Dịch thuật & Caching
                        similarity = difflib.SequenceMatcher(None, current_text, self.last_text).ratio()

                        if similarity < config.SIMILARITY_THRESHOLD:
                            self.last_text = current_text

                            # CƠ CHẾ DATABASE
                            if current_text in self.local_db:
                                # Nếu đã có trong DB -> Trả về luôn
                                cached_translation = self.local_db[current_text]
                                self.text_updated.emit(f"[DB] {cached_translation}")
                            else:
                                # Nếu chưa có -> Gọi API Grok
                                try:
                                    response = self.client.chat.completions.create(
                                        model=config.GROK_MODEL_NAME,
                                        messages=[ # type: ignore
                                            {
                                                "role": "system",
                                                "content": "Bạn là một dịch giả game chuyên nghiệp. Hãy dịch câu thoại sau sang tiếng Việt. Yêu cầu: văn phong mượt mà, tự suy luận quan hệ nhân vật để xưng hô chuẩn, giữ nguyên tên riêng. Tuyệt đối không giải thích, chỉ in ra bản dịch."
                                            },
                                            {
                                                "role": "user",
                                                "content": current_text
                                            }
                                        ],
                                        temperature=0.3
                                    )
                                    translated_text = response.choices[0].message.content.strip()

                                    # Lưu kết quả mới vào DB
                                    self.local_db[current_text] = translated_text
                                    self.save_db()

                                    self.text_updated.emit(translated_text)
                                except Exception as api_err:
                                    print(f"Lỗi API Grok: {api_err}")

                    except Exception as e:
                        print(f"Lỗi hệ thống: {e}")

                time.sleep(config.SCAN_INTERVAL_SECONDS)

    def stop(self):
        self.running = False
        self.quit()