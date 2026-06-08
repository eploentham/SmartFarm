"""Show camera 2 feed on TV (second display, half-screen) with countdown overlay."""
import cv2
import time
import os
from datetime import datetime
from picamera2 import Picamera2
from config import (CAM2_INDEX, TV_X_OFFSET, TV_Y_OFFSET, TV_WIDTH, TV_HEIGHT,
                    CAPTURE_DIR)
from tts_helper import speak_th

WINDOW = 'Chemical Capture'

class TvDisplay:
    def __init__(self):
        self.cam = Picamera2(camera_num=CAM2_INDEX)
        cfg = self.cam.create_still_configuration(
            main={'size': (1920, 1080), 'format': 'RGB888'})
        self.cam.configure(cfg)
        self.cam.set_controls({'AfMode': 2})         # continuous autofocus
        self.cam.start()
        time.sleep(1.0)                              # let AF settle

        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
        cv2.moveWindow(WINDOW, TV_X_OFFSET, TV_Y_OFFSET)
        cv2.resizeWindow(WINDOW, TV_WIDTH, TV_HEIGHT)

    def _get_bgr(self):
        frame = self.cam.capture_array()
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def show_live(self, seconds: int, instruction: str = ""):
        """Live feed with optional instruction text — for `seconds` total."""
        end = time.time() + seconds
        while time.time() < end:
            f = self._get_bgr()
            if instruction:
                cv2.putText(f, instruction, (40, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)
            cv2.imshow(WINDOW, f)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    def countdown_and_capture(self) -> str:
        """3-2-1 countdown with overlay + voice, then capture full-res still.
           Returns path to saved JPG."""
        for n in (3, 2, 1):
            speak_th(str(n))                         # voice "สาม สอง หนึ่ง"
            end = time.time() + 1.0
            while time.time() < end:
                f = self._get_bgr()
                # big number overlay, center
                h, w = f.shape[:2]
                txt = str(n)
                (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 8, 12)
                cv2.putText(f, txt, ((w - tw)//2, (h + th)//2),
                            cv2.FONT_HERSHEY_SIMPLEX, 8, (0, 0, 255), 12)
                cv2.imshow(WINDOW, f)
                cv2.waitKey(1)

        # Snap full-res
        speak_th("ถ่ายภาพ")
        fname = datetime.now().strftime('chem_%Y%m%d_%H%M%S.jpg')
        path = os.path.join(CAPTURE_DIR, fname)
        self.cam.capture_file(path)

        # Flash effect
        white = 255 * cv2.absdiff(self._get_bgr(), self._get_bgr())  # blank
        white[:] = 255
        cv2.imshow(WINDOW, white)
        cv2.waitKey(150)
        return path

    def show_message(self, lines: list[str], seconds: int = 3):
        """Plain text screen — used for 'Analyzing…' or 'Done!'."""
        img = cv2.copyMakeBorder(
            cv2.imread('/dev/null', 0) if False else
            cv2.UMat(TV_HEIGHT, TV_WIDTH, cv2.CV_8UC3).get() * 0,
            0, 0, 0, 0, cv2.BORDER_CONSTANT)
        import numpy as np
        img = np.zeros((TV_HEIGHT, TV_WIDTH, 3), dtype='uint8')
        for i, line in enumerate(lines):
            cv2.putText(img, line, (40, 100 + i * 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
        cv2.imshow(WINDOW, img)
        cv2.waitKey(1)
        time.sleep(seconds)

    def close(self):
        self.cam.stop()
        cv2.destroyWindow(WINDOW)