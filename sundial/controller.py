import datetime
import threading

from .config import TZ


class SundialController:
    def __init__(self):
        self.lock = threading.Lock()

        self.enabled = True
        self.use_pir = True

        self.rgb = {"r": 255, "g": 140, "b": 0}

        self.last_motion = False
        self.last_motion_text = "Neznámý"

    def get_state(self):
        with self.lock:
            return {
                "enabled": self.enabled,
                "use_pir": self.use_pir,
                "rgb": dict(self.rgb),
                "last_motion": self.last_motion,
                "last_motion_text": self.last_motion_text,
                "device_time": datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
            }

    def set_enabled(self, value: bool):
        with self.lock:
            self.enabled = bool(value)

    def set_use_pir(self, value: bool):
        with self.lock:
            self.use_pir = bool(value)

    def set_rgb(self, r: int, g: int, b: int):
        with self.lock:
            self.rgb["r"] = max(0, min(255, int(r)))
            self.rgb["g"] = max(0, min(255, int(g)))
            self.rgb["b"] = max(0, min(255, int(b)))

    def get_rgb(self):
        with self.lock:
            return self.rgb["r"], self.rgb["g"], self.rgb["b"]

    def is_enabled(self):
        with self.lock:
            return self.enabled

    def is_pir_enabled(self):
        with self.lock:
            return self.use_pir

    def set_motion(self, detected: bool):
        with self.lock:
            self.last_motion = bool(detected)
            self.last_motion_text = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")