#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import datetime
from zoneinfo import ZoneInfo
import pathlib
import socket
import struct
import threading

from PIL import Image, ImageDraw, ImageFont
from rpi_ws281x import PixelStrip, Color

import RPi.GPIO as GPIO
import ioexpander as io  # pimoroni-ioexpander

# ================== KONFIG ==================

TZ = ZoneInfo("Europe/Prague")

# LED pásek – používáme jen prvních N LED, protože zbytek je mrtvý
TOTAL_LED_COUNT = 15  # počet FUNKČNÍCH LED
LED_PIN = 18          # GPIO18 (pin 12)
LED_BRIGHTNESS = 128
LED_DMA = 10
LED_CHANNEL = 0

# Tlačítko
BUTTON_PIN = 20       # GPIO20 = pin 38, druhá noha tlačítka na GND (pin 39)

# RGB potenciometr (PIM523) – stejné zapojení jako v potentiometer.py
I2C_ADDR = 0x0E
POT_VREF = 3.3

PIN_RED = 1
PIN_GREEN = 7
PIN_BLUE = 2

POT_ENC_A = 12
POT_ENC_B = 3
POT_ENC_C = 11  # ADC pin potenciometru

BRIGHTNESS = 0.5
PWM_PERIOD = int(255 / BRIGHTNESS)  # pro ioexpander PWM

# E-paper (2.13" V4 Waveshare)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
base_dir = pathlib.Path(__file__).resolve().parent

try:
    font_big = ImageFont.truetype(FONT_PATH, 32)
    font_small = ImageFont.truetype(FONT_PATH, 16)
except Exception:
    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()

# --------- SMBUS COMPAT (pro případné smbus importy) ----------
try:
    import smbus  # pokud existuje, nic neřešíme
except ImportError:
    import smbus2 as smbus
    import sys as _sys
    _sys.modules["smbus"] = smbus

# --------- E-PAPER KNIHOVNA (bez touch) ----------
TP_LIB_PATH = "/home/jakub/Touch_e-Paper_Code/python/lib"
if os.path.isdir(TP_LIB_PATH):
    sys.path.append(TP_LIB_PATH)
else:
    print("VAROVÁNÍ: Nenalezena cesta k TP_lib:", TP_LIB_PATH)

from TP_lib import epd2in13_V4  # GT1151 NEPOUŽÍVÁME

# --- E-PAPER INIT ---
epd = epd2in13_V4.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

WIDTH, HEIGHT = epd.height, epd.width  # typicky 250x122
image = Image.new("1", (WIDTH, HEIGHT), 255)
draw = ImageDraw.Draw(image)

# ================== GLOBÁLNÍ STAV ==================

# LED pásek
strip = PixelStrip(
    TOTAL_LED_COUNT,
    LED_PIN,
    800000,
    LED_DMA,
    False,
    LED_BRIGHTNESS,
    LED_CHANNEL
)
strip.begin()


def clear_strip():
    for i in range(TOTAL_LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def set_strip_color(r, g, b):
    for i in range(TOTAL_LED_COUNT):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def led_selftest():
    print("LED selftest: R -> G -> B")
    for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
        for i in range(TOTAL_LED_COUNT):
            strip.setPixelColor(i, Color(*color))
        strip.show()
        time.sleep(0.5)
    clear_strip()


def set_single_led_for_hour(dt, r, g, b):
    """
    Svítí jen jedna LED podle hodiny.
    Použiju 12h mapování: 1..12 -> index 0..11.
    Když máš 15 funkčních LED, prvních 12 použijeme pro hodiny.
    """
    h12 = dt.hour % 12
    if h12 == 0:
        h12 = 12
    idx = h12 - 1  # 0..11

    for i in range(TOTAL_LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))

    if idx < TOTAL_LED_COUNT:
        strip.setPixelColor(idx, Color(r, g, b))

    strip.show()


# RGB stav
rgb_lock = threading.Lock()
rgb = {"r": 255, "g": 0, "b": 0}

# IOExpander / potenciometr
ioe = None

# Stav tlačítka a konfigurace
config_mode = False   # True = nastavujeme barvu
config_channel = None  # "r" / "g" / "b"
last_button_state = 1

# „chytrý“ refresh čísla z potenciometru
pot_raw_last = None
pot_displayed_val = None
pot_last_change_time = 0.0
POT_STABLE_SEC = 1.0
POT_JITTER_TOL = 3


# ================== RGB POT / IO EXPANDER ==================

def rgb_pot_init():
    """Inicializace IO expanderu pro RGB potenciometr podle potentiometer.py."""
    global ioe
    try:
        ioe = io.IOE(i2c_addr=I2C_ADDR)
        ioe.set_adc_vref(POT_VREF)

        # potenciometr – stejně jako v potentiometer.py
        ioe.set_mode(POT_ENC_A, io.PIN_MODE_PP)
        ioe.set_mode(POT_ENC_B, io.PIN_MODE_PP)
        ioe.set_mode(POT_ENC_C, io.ADC)

        ioe.output(POT_ENC_A, 1)
        ioe.output(POT_ENC_B, 0)

        # PWM pro RGB LED v knoflíku
        ioe.set_pwm_period(PWM_PERIOD)
        ioe.set_pwm_control(divider=2)

        ioe.set_mode(PIN_RED, io.PWM, invert=True)
        ioe.set_mode(PIN_GREEN, io.PWM, invert=True)
        ioe.set_mode(PIN_BLUE, io.PWM, invert=True)

        print("RGB potenciometr inicializován.")
    except Exception as e:
        print("RGB pot init fail:", repr(e))
        ioe = None


def read_pot_value_0_255():
    """Vrátí hodnotu potenciometru 0–255 z POT_ENC_C (pin 11)."""
    if ioe is None:
        return 0
    try:
        v = ioe.input(POT_ENC_C)  # v Voltech
    except Exception as e:
        print("read_pot_value_0_255: chyba při čtení ADC:", repr(e))
        return 0

    if v < 0:
        v = 0
    if v > POT_VREF:
        v = POT_VREF

    return int(round((v / POT_VREF) * 255))


def _scale_255_to_pwm(v):
    v = max(0, min(255, int(v)))
    return int(v * PWM_PERIOD / 255)


def set_pot_led_color(r, g, b):
    """Nastaví barvu LED v potenciometru (0–255)."""
    if ioe is None:
        return
    try:
        ioe.output(PIN_RED, _scale_255_to_pwm(r))
        ioe.output(PIN_GREEN, _scale_255_to_pwm(g))
        ioe.output(PIN_BLUE, _scale_255_to_pwm(b))
    except Exception as e:
        print("set_pot_led_color: chyba:", repr(e))


# ================== E-PAPER KRESLENÍ ==================

def draw_time_screen():
    """Hlavní „titulní“ obrazovka – jen čas uprostřed."""
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=255)
    now_txt = datetime.datetime.now(TZ).strftime("%H:%M")
    bbox = draw.textbbox((0, 0), now_txt, font=font_big)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((WIDTH - w) // 2, (HEIGHT - h) // 2), now_txt, font=font_big, fill=0)


def _channel_label(ch):
    if ch == "r":
        return "ČERVENÁ"
    if ch == "g":
        return "ZELENÁ"
    if ch == "b":
        return "MODRÁ"
    return "NEZNÁMÁ"


def draw_config_screen(channel, value):
    """
    Obrazovka při nastavování barvy:
    - název barvy (ČERVENÁ/ZELENÁ/MODRÁ)
    - pod tím číslo 0–255
    """
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=255)

    label = _channel_label(channel)

    bbox_label = draw.textbbox((0, 0), label, font=font_small)
    lw = bbox_label[2] - bbox_label[0]
    draw.text(((WIDTH - lw) // 2, 10), label, font=font_small, fill=0)

    val_txt = str(value)
    bbox_val = draw.textbbox((0, 0), val_txt, font=font_big)
    vw = bbox_val[2] - bbox_val[0]
    vh = bbox_val[3] - bbox_val[1]
    draw.text(((WIDTH - vw) // 2, (HEIGHT - vh) // 2), val_txt, font=font_big, fill=0)


# ================== TLAČÍTKO A KONFIGURACE ==================

def _reset_pot_tracking(initial_val):
    global pot_raw_last, pot_displayed_val, pot_last_change_time
    pot_raw_last = initial_val
    pot_displayed_val = initial_val
    pot_last_change_time = time.monotonic()


def enter_config_mode():
    global config_mode, config_channel
    config_mode = True
    config_channel = "r"
    print("=== VSTUP DO REŽIMU NASTAVENÍ BARVY (R) ===")

    with rgb_lock:
        val = rgb["r"]

    _reset_pot_tracking(val)
    set_pot_led_color(val, 0, 0)

    draw_config_screen("r", val)
    epd.displayPartial(epd.getbuffer(image))


def advance_config_channel():
    global config_channel

    if config_channel == "r":
        config_channel = "g"
        print("PŘEPÍNÁM NA G")
        with rgb_lock:
            val = rgb["g"]
        _reset_pot_tracking(val)
        set_pot_led_color(0, val, 0)
        draw_config_screen("g", val)
        epd.displayPartial(epd.getbuffer(image))

    elif config_channel == "g":
        config_channel = "b"
        print("PŘEPÍNÁM NA B")
        with rgb_lock:
            val = rgb["b"]
        _reset_pot_tracking(val)
        set_pot_led_color(0, 0, val)
        draw_config_screen("b", val)
        epd.displayPartial(epd.getbuffer(image))

    elif config_channel == "b":
        exit_config_mode()


def exit_config_mode():
    global config_mode, config_channel
    config_mode = False
    config_channel = None
    print("=== KONEC NASTAVOVÁNÍ BARVY ===")

    with rgb_lock:
        r, g, b = rgb["r"], rgb["g"], rgb["b"]

    # návrat: pot i pásek na finální barvu
    set_pot_led_color(r, g, b)
    set_single_led_for_hour(datetime.datetime.now(TZ), r, g, b)

    draw_time_screen()
    epd.displayPartial(epd.getbuffer(image))


def handle_button_press():
    if not config_mode:
        print("[BTN] klik mimo config -> enter_config_mode()")
        enter_config_mode()
    else:
        print("[BTN] klik v config -> advance_config_channel()")
        advance_config_channel()


# ================== NTP SYNC ==================

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


# ================== HLAVNÍ SMYČKA ==================

def main_loop():
    global last_button_state, pot_raw_last, pot_displayed_val, pot_last_change_time

    last_button_state = GPIO.input(BUTTON_PIN)
    print(f"[INIT] BUTTON initial state = {last_button_state} (1 = uvolněno)")

    # výchozí barva na pásku i potíku
    with rgb_lock:
        r, g, b = rgb["r"], rgb["g"], rgb["b"]
    set_single_led_for_hour(datetime.datetime.now(TZ), r, g, b)
    set_pot_led_color(r, g, b)

    last_minute = None

    while True:
        now_dt = datetime.datetime.now(TZ)

        # titulní režim: jedna LED podle hodiny + refresh času na displeji po minutě
        if not config_mode:
            with rgb_lock:
                r, g, b = rgb["r"], rgb["g"], rgb["b"]
            set_single_led_for_hour(now_dt, r, g, b)

            if last_minute is None or now_dt.minute != last_minute:
                last_minute = now_dt.minute
                print(f"[TIME] MINUTA -> {last_minute}, refresh e-paper (čas)")
                draw_time_screen()
                epd.displayPartial(epd.getbuffer(image))

        # tlačítko – hrana HIGH->LOW
        cur = GPIO.input(BUTTON_PIN)
        if cur != last_button_state:
            print("Tlačítko =", cur)
            if cur == GPIO.LOW:
                print("[BTN] STISK")
                handle_button_press()
            else:
                print("[BTN] UVOLNĚNÍ")
            last_button_state = cur

        # config režim – stabilní hodnota po 1s
        if config_mode and config_channel is not None:
            val = read_pot_value_0_255()
            now_mono = time.monotonic()

            if pot_raw_last is None:
                pot_raw_last = val
                pot_displayed_val = val
                pot_last_change_time = now_mono

            if abs(val - pot_raw_last) > POT_JITTER_TOL:
                pot_raw_last = val
                pot_last_change_time = now_mono

            if (now_mono - pot_last_change_time) >= POT_STABLE_SEC and val != pot_displayed_val:
                pot_displayed_val = val
                print(f"[POT] STABILNÍ hodnota {config_channel.upper()} = {val}")

                with rgb_lock:
                    if config_channel == "r":
                        rgb["r"] = val
                    elif config_channel == "g":
                        rgb["g"] = val
                    elif config_channel == "b":
                        rgb["b"] = val
                    r, g, b = rgb["r"], rgb["g"], rgb["b"]

                set_single_led_for_hour(datetime.datetime.now(TZ), r, g, b)

                if config_channel == "r":
                    set_pot_led_color(val, 0, 0)
                elif config_channel == "g":
                    set_pot_led_color(0, val, 0)
                elif config_channel == "b":
                    set_pot_led_color(0, 0, val)

                draw_config_screen(config_channel, val)
                epd.displayPartial(epd.getbuffer(image))

        time.sleep(0.02)


def main():
    sync_time_at_start()

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    rgb_pot_init()
    led_selftest()

    draw_time_screen()
    epd.display(epd.getbuffer(image))

    epd.init(epd.PART_UPDATE)

    main_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Ukončuji...")
        clear_strip()
        GPIO.cleanup()
        try:
            epd.sleep()
        except Exception:
            pass
        print("Hotovo.")