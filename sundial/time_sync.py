import os
import socket
import struct
import datetime

from .config import TZ


def _ntp_get_time_epoch(server="pool.ntp.org", timeout=2.0):
    NTP_PORT = 123
    NTP_DELTA = 2208988800

    msg = b"\x1b" + 47 * b"\0"
    addr = (server, NTP_PORT)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.sendto(msg, addr)
        data, _ = s.recvfrom(1024)

    if len(data) < 48:
        raise RuntimeError("NTP odpověď je příliš krátká")

    t = struct.unpack("!12I", data)[10]
    return t - NTP_DELTA


def sync_time_at_start():
    try:
        epoch = _ntp_get_time_epoch("pool.ntp.org", timeout=2.0)
        dt = datetime.datetime.fromtimestamp(epoch, TZ)

        os.system("timedatectl set-ntp false >/dev/null 2>&1")
        os.system(f'date -s "{dt.strftime("%Y-%m-%d %H:%M:%S")}" >/dev/null 2>&1')
        os.system("timedatectl set-ntp true >/dev/null 2>&1")

        print(f"[TIME] NTP sync OK -> {dt.strftime('%Y-%m-%d %H:%M:%S')} {TZ}")
    except Exception as e:
        print("[TIME] NTP sync FAIL:", repr(e))
