"""
sundial/controller.py
=====================
Sdílený stav zařízení.

Tento objekt je „single source of truth" – drží všechny hodnoty, které
se mění buď z fyzického hardware (tlačítko, potenciometr, PIR)
nebo ze vzdáleného API (AzureSync). Veškerý přístup je thread-safe
díky jednomu zámku (threading.Lock).
"""

import datetime
import threading

from .config import TZ


class SundialController:
    def __init__(self):
        self.lock = threading.Lock()

        # Zda jsou hodiny celkově aktivní (přepínač z webu / Azure)
        self.enabled  = True
        # Zda řízení provádí PIR senzor (True) nebo hodiny svítí vždy (False)
        self.use_pir  = True

        # Aktuální barva LED pásku (výchozí: teplá oranžová)
        self.rgb = {"r": 255, "g": 140, "b": 0}

        # Poslední zjištěný stav pohybu + čas změny (zobrazuje se na webu)
        self.last_motion      = False
        self.last_motion_text = "Neznámý"

    # ── Čtení celého stavu (pro API /state a AzureSync push) ──

    def get_state(self) -> dict:
        with self.lock:
            return {
                "enabled":          self.enabled,
                "use_pir":          self.use_pir,
                "rgb":              dict(self.rgb),
                "last_motion":      self.last_motion,
                "last_motion_text": self.last_motion_text,
                "device_time":      datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
            }

    # ── Settery (volají AzureSync nebo main_loop) ──

    def set_enabled(self, value: bool):
        with self.lock:
            self.enabled = bool(value)

    def set_use_pir(self, value: bool):
        with self.lock:
            self.use_pir = bool(value)

    def set_rgb(self, r: int, g: int, b: int):
        """Nastaví RGB, hodnoty jsou vždy oříznuty na 0–255."""
        with self.lock:
            self.rgb["r"] = max(0, min(255, int(r)))
            self.rgb["g"] = max(0, min(255, int(g)))
            self.rgb["b"] = max(0, min(255, int(b)))

    def set_motion(self, detected: bool):
        """Zaznamenává aktuální stav PIR a timestamp poslední změny."""
        with self.lock:
            self.last_motion      = bool(detected)
            self.last_motion_text = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

    # ── Gettery ──

    def get_rgb(self) -> tuple[int, int, int]:
        with self.lock:
            return self.rgb["r"], self.rgb["g"], self.rgb["b"]

    def is_enabled(self) -> bool:
        with self.lock:
            return self.enabled

    def is_pir_enabled(self) -> bool:
        with self.lock:
            return self.use_pir
