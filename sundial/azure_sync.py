"""
sundial/azure_sync.py
=====================
Nahrazuje lokální Flask webapp.
RPi každé POLL_INTERVAL sekund:
  1. stáhne stav z Azure Functions  → aplikuje na hardware (controller)
  2. pushne device_time + last_motion zpět do Azure
"""

import datetime
import logging
import os
import time

import requests

from .config import TZ

log = logging.getLogger("azure_sync")

# URL Azure Functions – nastav přes env proměnnou nebo přímo zde.
# Příklad: "https://func-sundial-abc123.azurewebsites.net"
AZURE_API_URL = os.getenv("SUNDIAL_API_URL", "https://YOUR_FUNC_APP.azurewebsites.net")

POLL_INTERVAL = 2.0   # sekund mezi staženími stavu
PUSH_INTERVAL = 5.0   # sekund mezi pushem live dat (device_time, pohyb)
REQUEST_TIMEOUT = 3   # timeout HTTP požadavku v sekundách


class AzureSync:
    """
    Synchronizuje stav mezi Azure Storage Table a lokálním controllerem.

    Použití v main.py:
        sync = AzureSync(controller)
        # V hlavní smyčce každé 2s:
        sync.tick()
    """

    def __init__(self, controller):
        self.controller = controller
        self._last_poll = 0.0
        self._last_push = 0.0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})
        log.info("AzureSync init, API: %s", AZURE_API_URL)

    # ── Veřejné API ───────────────────────────────────────────────────────────

    def tick(self):
        """Zavolej jednou za iteraci hlavní smyčky (~20ms)."""
        now = time.monotonic()

        if now - self._last_poll >= POLL_INTERVAL:
            self._poll()
            self._last_poll = now

        if now - self._last_push >= PUSH_INTERVAL:
            self._push()
            self._last_push = now

    # ── Interní metody ────────────────────────────────────────────────────────

    def _poll(self):
        """Stáhne stav z Azure a aplikuje ho na controller."""
        try:
            resp = self._session.get(
                f"{AZURE_API_URL}/api/state",
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            rgb = data.get("rgb", {})
            self.controller.set_rgb(
                rgb.get("r", 255),
                rgb.get("g", 140),
                rgb.get("b", 0),
            )
            self.controller.set_enabled(data.get("enabled", True))
            self.controller.set_use_pir(data.get("use_pir", True))

            log.debug("Poll OK: enabled=%s pir=%s rgb=%s",
                      data.get("enabled"), data.get("use_pir"), rgb)

        except requests.RequestException as e:
            log.warning("Poll failed: %s", e)

    def _push(self):
        """Pushne živý stav RPi (čas, pohyb) do Azure."""
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
            log.debug("Push OK: device_time=%s", now_str)

        except requests.RequestException as e:
            log.warning("Push failed: %s", e)
