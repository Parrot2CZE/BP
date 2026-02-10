#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import threading
import datetime
from zoneinfo import ZoneInfo
import pathlib

from PIL import Image, ImageDraw, ImageFont
from rpi_ws281x import PixelStrip, Color
import serial

# ================== KONFIG ==================
# LED pásek
TOTAL_LED_COUNT   = 144   # skutečný počet LED na pásku
SUNDIAL_LED_COUNT = 12    # prvních 12 LED jako hodiny
SUNDIAL_OFFSET    = 0     # pokud jsi první LED odřízl, dej 1 atd.
LED_PIN           = 18    # GPIO18 (pin 12)
LED_BRIGHTNESS    = 128
LED_DMA           = 10
LED_CHANNEL       = 0

# TFmini
SERIAL_DEV  = "/dev/serial0"
SERIAL_BAUD = 115200

# Časová zóna
TZ = ZoneInfo("Europe/Prague")

# E-paper Waveshare (2.13" V4 – zobrazování)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# ============================================

base_dir = pathlib.Path(__file__).resolve().parent

try:
    font_big = ImageFont.truetype(FONT_PATH, 24)
    font_small = ImageFont.truetype(FONT_PATH, 14)
except:
    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()

# --------- SMBUS COMPAT (pro TP_lib, které dělá `from smbus import SMBus`) ----------
try:
    import smbus  # pokud existuje, nic neřešíme
except ImportError:
    # použijeme smbus2 a nasimuluje se modul "smbus"
    import smbus2 as smbus
    import sys as _sys
    _sys.modules['smbus'] = smbus

# --------- TOUCH + E-PAPER KNIHOVNA (z Touch_e-Paper_Code) ----------
TP_LIB_PATH = "/home/jakub/Touch_e-Paper_Code/python/lib"
if os.path.isdir(TP_LIB_PATH):
    sys.path.append(TP_LIB_PATH)
else:
    print("VAROVÁNÍ: Nenalezena cesta k TP_lib:", TP_LIB_PATH)

from TP_lib import gt1151, epd2in13_V4

# --- E-PAPER ---
epd = epd2in13_V4.EPD()
epd.init(epd.FULL_UPDATE)
epd.Clear(0xFF)

# Pozor: u Waveshare bývá width/height prohozené
WIDTH, HEIGHT = epd.height, epd.width  # typicky 250x122
image = Image.new('1', (WIDTH, HEIGHT), 255)
draw = ImageDraw.Draw(image)

# --- TOUCH ---
gt = gt1151.GT1151()
GT_Dev = gt1151.GT_Development()
GT_Old = gt1151.GT_Development()

TOUCH_OK = True
try:
    ver = gt.GT_Init()
    print("Touch GT1151 inicializován OK.")
except Exception as e:
    print("Touch init failed, běžím bez touch:", e)
    TOUCH_OK = False

TOUCH_THREAD_RUNNING = False

def touch_irq_thread():
    """
    Kopie logiky z Waveshare: sleduje INT pin a nastavuje GT_Dev.Touch = 1/0.
    GT_Scan pak ví, jestli je prst přiložený.
    """
    global TOUCH_THREAD_RUNNING
    TOUCH_THREAD_RUNNING = True
    print("Touch IRQ thread start")
    while TOUCH_OK and TOUCH_THREAD_RUNNING:
        try:
            if gt.digital_read(gt.INT) == 0:
                GT_Dev.Touch = 1
            else:
                GT_Dev.Touch = 0
        except Exception:
            # nechceme zabít thread kvůli jedné chybě
            pass
        time.sleep(0.01)
    print("Touch IRQ thread end")

# --------- GLOBÁLNÍ RGB STAV (barva LED) ----------
rgb_lock = threading.Lock()
rgb = {"r": 255, "g": 0, "b": 0}

# --------- LED PÁSEK INIT ----------
strip = PixelStrip(TOTAL_LED_COUNT, LED_PIN, 800000, LED_DMA,
                   False, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

def clear_strip():
    for i in range(TOTAL_LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()

def set_sundial_led(hour12, r, g, b):
    """
    hour12: 1–12
    rozsvítí jednu LED podle hodiny, ostatní zhasne
    """
    index = (hour12 - 1) % SUNDIAL_LED_COUNT
    clear_strip()
    led_pos = (index + SUNDIAL_OFFSET) % TOTAL_LED_COUNT
    strip.setPixelColor(led_pos, Color(r, g, b))
    strip.show()

def led_selftest():
    """
    Krátký test: celý pásek R -> G -> B.
    Když se nic nezmění, data se k pásku nedostanou.
    """
    print("LED selftest: R -> G -> B")
    for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
        for i in range(TOTAL_LED_COUNT):
            strip.setPixelColor(i, Color(*color))
        strip.show()
        time.sleep(0.5)
    clear_strip()

# --------- TFmini: čtení ve vlákně ----------
ser = serial.Serial(SERIAL_DEV, SERIAL_BAUD, timeout=0.05)

def tfmini_loop():
    while True:
        first = ser.read(1)
        if first != b'Y':
            continue
        second = ser.read(1)
        if second != b'Y':
            continue
        frame = ser.read(7)
        if len(frame) < 7:
            continue
        b0, b1, b2, b3, *_ = frame
        dist = b0 + (b1 << 8)
        strength = b2 + (b3 << 8)
        print(f"TFmini: {dist:4d} cm | strength={strength:4d}")
        time.sleep(0.05)

# --------- E-PAPER UI: SLIDERY ----------
SLIDER_MARGIN_X = 10
SLIDER_WIDTH = WIDTH - 2 * SLIDER_MARGIN_X
SLIDER_HEIGHT = 16

R_Y = 50
G_Y = 80
B_Y = 110

def draw_ui():
    """
    Překreslí e-paper: čas (HH:MM, 12h AM/PM) + tři "slidery" R,G,B.
    Jen kreslí do 'image' – samotný refresh dělá volající.
    """
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=255)
    # jen hodiny:minuty v 12h formátu
    now = datetime.datetime.now(TZ).strftime("%I:%M %p")

    # čas nahoře
    try:
        bbox = draw.textbbox((0, 0), now, font=font_big)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except AttributeError:
        tw, th = font_big.getsize(now)
    draw.text(((WIDTH - tw) // 2, 5), now, font=font_big, fill=0)

    with rgb_lock:
        r, g, b = rgb["r"], rgb["g"], rgb["b"]

    def draw_slider(y, value, label):
        x0 = SLIDER_MARGIN_X
        y0 = y
        x1 = x0 + SLIDER_WIDTH
        y1 = y0 + SLIDER_HEIGHT
        draw.rectangle((x0, y0, x1, y1), outline=0, fill=255)
        fill_w = int(SLIDER_WIDTH * (value / 255.0))
        if fill_w > 0:
            draw.rectangle((x0 + 1, y0 + 1, x0 + fill_w, y1 - 1), fill=0)
        text = f"{label}: {value}"
        draw.text((x0, y0 - 16), text, font=font_small, fill=0)

    draw_slider(R_Y, r, "R")
    draw_slider(G_Y, g, "G")
    draw_slider(B_Y, b, "B")

def x_to_value(x):
    """
    Převede dotykové X v rozsahu [0, WIDTH] na hodnotu 0–255.
    """
    if x < SLIDER_MARGIN_X:
        x = SLIDER_MARGIN_X
    if x > SLIDER_MARGIN_X + SLIDER_WIDTH:
        x = SLIDER_MARGIN_X + SLIDER_WIDTH
    rel = (x - SLIDER_MARGIN_X) / SLIDER_WIDTH
    return int(rel * 255)

def handle_touch(x, y):
    """
    Zpracuje dotyk – podle Y vybere slider R/G/B, podle X nastaví novou hodnotu.
    Pak překreslí UI a změní barvu LED.
    """
    global rgb
    updated = False

    with rgb_lock:
        r, g, b = rgb["r"], rgb["g"], rgb["b"]

        if R_Y <= y <= R_Y + SLIDER_HEIGHT:
            r = x_to_value(x)
            rgb["r"] = r
            updated = True
            print(f"UPDATE R -> {r}")
        elif G_Y <= y <= G_Y + SLIDER_HEIGHT:
            g = x_to_value(x)
            rgb["g"] = g
            updated = True
            print(f"UPDATE G -> {g}")
        elif B_Y <= y <= B_Y + SLIDER_HEIGHT:
            b = x_to_value(x)
            rgb["b"] = b
            updated = True
            print(f"UPDATE B -> {b}")

    if updated:
        now = datetime.datetime.now(TZ)
        hour = now.hour
        hour12 = hour % 12 or 12
        with rgb_lock:
            set_sundial_led(hour12, rgb["r"], rgb["g"], rgb["b"])
        # překreslit celé UI a dát partial refresh
        draw_ui()
        epd.displayPartial(epd.getbuffer(image))

# --------- DOTYK – čtení z GT1151 ----------
def get_touch():
    """
    Vrátí (x, y) v souřadnicích displeje, nebo None když není dotyk.
    Logika vychází z Waveshare dema:
      - GT_Scan(GT_Dev, GT_Old)
      - používáme TouchpointFlag
    """
    if not TOUCH_OK:
        return None

    try:
        gt.GT_Scan(GT_Dev, GT_Old)
    except Exception:
        return None

    if GT_Dev.TouchpointFlag:
        GT_Dev.TouchpointFlag = 0
        x = GT_Dev.X[0]
        y = GT_Dev.Y[0]
        if x == 0 and y == 0:
            return None
        print(f"TOUCH RAW: x={x}, y={y}")
        return (x, y)

    return None

# --------- HLAVNÍ LOGIKA: HODINY + TOUCH ----------
def sundial_and_touch_loop():
    """
    Hlavní smyčka:
      - sleduje změnu hodiny (1–12) a při změně přepne LED
      - sleduje změnu minuty a při každé nové minutě překreslí čas na e-paper (partial)
      - průběžně čte dotyk a podle něj mění RGB + e-paper UI
    """
    last_hour12 = None
    last_minute = None

    # počáteční vykreslení UI (už proběhlo, ale nevadí)
    draw_ui()

    while True:
        now = datetime.datetime.now(TZ)
        hour = now.hour
        minute = now.minute

        hour12 = hour % 12
        if hour12 == 0:
            hour12 = 12

        # pokud se změnila hodina → přepni "hodinovou" LED
        if hour12 != last_hour12:
            with rgb_lock:
                r, g, b = rgb["r"], rgb["g"], rgb["b"]
            print(f"HODINA -> {hour12}, LED barva = ({r},{g},{b})")
            set_sundial_led(hour12, r, g, b)
            last_hour12 = hour12

        # pokud se změnila minuta → překresli čas + slidery (partial)
        if minute != last_minute:
            print(f"MINUTA -> {minute}, refresh e-paper (partial)")
            draw_ui()
            epd.displayPartial(epd.getbuffer(image))
            last_minute = minute

        # dotyk – pokud nějaký je, zpracuj ho
        touch = get_touch()
        if touch is not None:
            tx, ty = touch
            handle_touch(tx, ty)

        time.sleep(0.05)

# --------- START PROGRAMU ----------
if __name__ == "__main__":
    print("Start: sluneční hodiny (12 LED, 12h AM/PM), TFmini → konzole, RGB přes touch na e-paperu")

    led_selftest()

    now = datetime.datetime.now(TZ)
    hour = now.hour
    hour12 = hour % 12 or 12
    with rgb_lock:
        set_sundial_led(hour12, rgb["r"], rgb["g"], rgb["b"])

    # první vykreslení – full update
    draw_ui()
    epd.display(epd.getbuffer(image))

    # přepnout do partial režimu pro další změny
    epd.init(epd.PART_UPDATE)

    # touch IRQ thread – jako v originálním demu
    if TOUCH_OK:
        t_touch = threading.Thread(target=touch_irq_thread, daemon=True)
        t_touch.start()

    t_tf = threading.Thread(target=tfmini_loop, daemon=True)
    t_tf.start()

    try:
        sundial_and_touch_loop()
    except KeyboardInterrupt:
        print("Ukončuji...")
        clear_strip()
        try:
            epd.sleep()
        except:
            pass
        try:
            ser.close()
        except:
            pass
        TOUCH_THREAD_RUNNING = False
        print("Hotovo.")
