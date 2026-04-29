"""
sundial/azure_sync.py
=====================
RPi každé POLL_INTERVAL sekund:
  1. stáhne stav z Azure Functions  → aplikuje na hardware (controller)
  2. pushne device_time + last_motion zpět do Azure

HTTP volání běží ve vlákně na pozadí – hlavní smyčka hodin
není blokována ani při dlouhém cold startu Azure Functions.
"""

import datetime
import logging
import os
import threading
import time

import requests

from .config import TZ

log = logging.getLogger("azure_sync")

AZURE_API_URL   = os.getenv("SUNDIAL_API_URL", "https://func-sundial-waal5652j36s6.azurewebsites.net")

POLL_INTERVAL   = 5.0    # sekund mezi staženími stavu
PUSH_INTERVAL   = 10.0   # sekund mezi pushem live dat
REQUEST_TIMEOUT = 15     # timeout pro jeden HTTP požadavek


class AzureSync:
    def __init__(self, controller):
        self.controller = controller
        self._last_poll = 0.0
        self._last_push = 0.0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        self._config_mode = False  # když True, RGB se z Azure nepřepisuje
        log.info("AzureSync init, API: %s", AZURE_API_URL)

    def set_config_mode(self, active: bool):
        """Zavolej při vstupu/výstupu z config režimu."""
        self._config_mode = active

    def tick(self):
        """Zavolej jednou za iteraci hlavní smyčky (~20ms). Neblokuje."""
        now = time.monotonic()

        if now - self._last_poll >= POLL_INTERVAL:
            self._last_poll = now
            self._run_in_background(self._poll)

        if now - self._last_push >= PUSH_INTERVAL:
            self._last_push = now
            self._run_in_background(self._push)

    def push_rgb_now(self):
        """Okamžitě pushne aktuální RGB do Azure (zavolej po skončení config módu)."""
        self._run_in_background(self._push_rgb)

    def _run_in_background(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        t.start()

    def _poll(self):
        try:
            resp = self._session.get(
                f"{AZURE_API_URL}/api/state",
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            rgb = data.get("rgb", {})

            # RGB přepisujeme jen když uživatel neprovádí fyzické nastavení
            if not self._config_mode:
                self.controller.set_rgb(
                    rgb.get("r", 255),
                    rgb.get("g", 140),
                    rgb.get("b", 0),
                )

            self.controller.set_enabled(data.get("enabled", True))
            self.controller.set_use_pir(data.get("use_pir", True))

            print(f"[AZURE] Poll OK – RGB({rgb.get('r')},{rgb.get('g')},{rgb.get('b')}) "
                  f"enabled={data.get('enabled')} pir={data.get('use_pir')}"
                  + (" [config mode – RGB ignorováno]" if self._config_mode else ""))

        except requests.RequestException as e:
            print(f"[AZURE] Poll failed: {e}")

    def _push(self):
        try:
            state = self.controller.get_state()
            now_str = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

            self._session.post(
                f"{AZURE_API_URL}/api/state",
                json={
                    "device_time":      now_str,
                    "last_motion":      state.get("last_motion", False),
                    "last_motion_text": state.get("last_motion_text", "—"),
                },
                timeout=REQUEST_TIMEOUT,
            )
            print(f"[AZURE] Push OK – device_time={now_str}")

        except requests.RequestException as e:
            print(f"[AZURE] Push failed: {e}")

    def _push_rgb(self):
        """Pushne aktuální RGB hodnotu do Azure."""
        try:
            r, g, b = self.controller.get_rgb()
            self._session.post(
                f"{AZURE_API_URL}/api/rgb",
                json={"r": r, "g": g, "b": b},
                timeout=REQUEST_TIMEOUT,
            )
            print(f"[AZURE] Push RGB OK – ({r},{g},{b})")

        except requests.RequestException as e:
            print(f"[AZURE] Push RGB failed: {e}")
