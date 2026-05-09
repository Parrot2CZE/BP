"""
sundial/azure_sync.py
=====================
Obousměrná synchronizace s Azure Functions API.

Co dělá:
  POLL (každých POLL_INTERVAL s)
    – stáhne stav z /api/state
    – aplikuje enabled, use_pir a RGB na controller
    – RGB se ignoruje, pokud probíhá fyzický config režim (set_config_mode(True))

  PUSH (každých PUSH_INTERVAL s)
    – pošle device_time, last_motion a last_motion_text do /api/state

  push_rgb_now()
    – jednorázový okamžitý push RGB po skončení config režimu,
      aby se nová barva dostala do Azure dřív než příští pravidelný poll

Všechna HTTP volání běží ve vlastních daemonních vláknech → hlavní smyčka
není nikdy zablokována, ani při dlouhém cold-startu Azure Functions.
"""

import datetime
import logging
import os
import threading
import time

import requests

from .config import TZ

log = logging.getLogger("azure_sync")

# URL Azure Functions – přepíše ho env proměnná SUNDIAL_API_URL (volitelné)
AZURE_API_URL = os.getenv(
    "SUNDIAL_API_URL",
    "https://func-sundial-waal5652j36s6.azurewebsites.net"
)

POLL_INTERVAL   = 5.0    # sekund mezi staženími stavu z Azure
PUSH_INTERVAL   = 10.0   # sekund mezi pushem live dat do Azure
REQUEST_TIMEOUT = 15     # max sekund na jeden HTTP požadavek


class AzureSync:
    def __init__(self, controller):
        self.controller    = controller
        self._last_poll    = 0.0
        self._last_push    = 0.0
        self._config_mode  = False   # příznak: fyzický config = nepřepisovat RGB z Azure

        # Sdílená session šetří handshaky (keep-alive)
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

        log.info("AzureSync init, API: %s", AZURE_API_URL)

    def set_config_mode(self, active: bool):
        """
        Voláme z main.py při vstupu / výstupu z fyzického config režimu.
        Dokud je active=True, poll ignoruje příchozí RGB z Azure.
        """
        self._config_mode = active

    def tick(self):
        """
        Voláme jednou za iteraci hlavní smyčky (~20 ms).
        Zkontroluje, zda uplynul čas na poll nebo push, a pokud ano,
        spustí příslušnou metodu v pozadí.
        """
        now = time.monotonic()

        if now - self._last_poll >= POLL_INTERVAL:
            self._last_poll = now
            self._run_in_background(self._poll)

        if now - self._last_push >= PUSH_INTERVAL:
            self._last_push = now
            self._run_in_background(self._push)

    def push_rgb_now(self):
        """Okamžitý push RGB (zavolej hned po exit_config_mode)."""
        self._run_in_background(self._push_rgb)

    # ── Interní metody ──

    def _run_in_background(self, fn):
        """Spustí funkci ve vlastním daemonním vlákně."""
        threading.Thread(target=fn, daemon=True).start()

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

            if not self._config_mode:
                # Normální provoz: Azure je zdrojem pravdy pro RGB
                self.controller.set_rgb(
                    rgb.get("r", 255),
                    rgb.get("g", 140),
                    rgb.get("b", 0),
                )

            self.controller.set_enabled(data.get("enabled", True))
            self.controller.set_use_pir(data.get("use_pir", True))

            note = " [config mode – RGB ignorováno]" if self._config_mode else ""
            print(
                f"[AZURE] Poll OK – RGB({rgb.get('r')},{rgb.get('g')},{rgb.get('b')}) "
                f"enabled={data.get('enabled')} pir={data.get('use_pir')}{note}"
            )

        except requests.RequestException as e:
            print(f"[AZURE] Poll failed: {e}")

    def _push(self):
        """Pošle live data (čas zařízení + stav pohybu) do Azure."""
        try:
            state   = self.controller.get_state()
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
        """Jednorázový push aktuálního RGB do /api/rgb."""
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
