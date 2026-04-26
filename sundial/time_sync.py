import os
import datetime
import urllib.request
import json

from .config import TZ


def _get_time_from_api(timeout: float = 5.0) -> int:
    """Stáhne aktuální čas z timeapi.io přes HTTPS. Vrátí Unix timestamp."""
    url = "https://timeapi.io/api/time/current/zone?timeZone=Europe%2FPrague"
    req = urllib.request.Request(url, headers={"User-Agent": "sundial-pi/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    # data["dateTime"] = "2026-04-18T12:17:55.123456"
    dt = datetime.datetime.fromisoformat(data["dateTime"].split(".")[0])
    dt = dt.replace(tzinfo=TZ)
    return int(dt.timestamp())


def sync_time_at_start():
    try:
        epoch = _get_time_from_api(timeout=5.0)
        dt = datetime.datetime.fromtimestamp(epoch, TZ)

        os.system("timedatectl set-ntp false >/dev/null 2>&1")
        os.system(f'date -s "{dt.strftime("%Y-%m-%d %H:%M:%S")}" >/dev/null 2>&1')
        os.system("timedatectl set-ntp true >/dev/null 2>&1")

        print(f"[TIME] HTTP sync OK -> {dt.strftime('%Y-%m-%d %H:%M:%S')} {TZ}")
    except Exception as e:
        print(f"[TIME] HTTP sync FAIL: {repr(e)}")
        print("[TIME] Pokračuji s interním časem zařízení.")
