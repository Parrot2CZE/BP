#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import datetime
import threading

import RPi.GPIO as GPIO

from .config import TZ, BUTTON_PIN
from .led_strip import LedStrip
from .rgb_pot import RGBPot
from .epaper_display import EpaperDisplay
from .time_sync import sync_time_at_start
from .pir_sensor import PirSensor


# ---------- globální stav aplikace (non-hw) ----------

rgb_lock = threading.Lock()
rgb = {"r": 255, "g": 0, "b": 0}

config_mode = False        # True = nastavujeme barvu
config_channel = None      # "r" / "g" / "b"
last_button_state = 1

# chytré čtení potenciometru
pot_raw_last = None
pot_displayed_val = None
pot_last_change_time = 0.0
POT_STABLE_SEC = 1.0
POT_JITTER_TOL = 3


def _reset_pot_tracking(initial_val):
    global pot_raw_last, pot_displayed_val, pot_last_change_time
    pot_raw_last = initial_val
    pot_displayed_val = initial_val
    pot_last_change_time = time.monotonic()


# ---------- režim konfigurace barvy ----------

def enter_config_mode(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip):
    global config_mode, config_channel
    config_mode = True
    config_channel = "r"
    print("=== VSTUP DO REŽIMU NASTAVENÍ BARVY (R) ===")

    with rgb_lock:
        val = rgb["r"]

    _reset_pot_tracking(val)
    pot.set_led_color(val, 0, 0)

    epaper.refresh_config("r", val)


def advance_config_channel(epaper: EpaperDisplay, pot: RGBPot):
    global config_channel

    if config_channel == "r":
        config_channel = "g"
        print("PŘEPÍNÁM NA G")
        with rgb_lock:
            val = rgb["g"]
        _reset_pot_tracking(val)
        pot.set_led_color(0, val, 0)
        epaper.refresh_config("g", val)

    elif config_channel == "g":
        config_channel = "b"
        print("PŘEPÍNÁM NA B")
        with rgb_lock:
            val = rgb["b"]
        _reset_pot_tracking(val)
        pot.set_led_color(0, 0, val)
        epaper.refresh_config("b", val)

    elif config_channel == "b":
        exit_config_mode(epaper, pot)


def exit_config_mode(epaper: EpaperDisplay, pot: RGBPot):
    global config_mode, config_channel
    config_mode = False
    config_channel = None
    print("=== KONEC NASTAVOVÁNÍ BARVY ===")

    with rgb_lock:
        r, g, b = rgb["r"], rgb["g"], rgb["b"]

    pot.set_led_color(r, g, b)

    # displej zpět na čas
    epaper.refresh_time()


def handle_button_press(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip):
    if not config_mode:
        print("[BTN] klik mimo config -> enter_config_mode()")
        enter_config_mode(epaper, pot, strip)
    else:
        print("[BTN] klik v config -> advance_config_channel()")
        advance_config_channel(epaper, pot)


# ---------- hlavní smyčka ----------

def main_loop(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip, pir: PirSensor):
    global last_button_state, pot_raw_last, pot_displayed_val, pot_last_change_time

    last_button_state = GPIO.input(BUTTON_PIN)
    print(f"[INIT] BUTTON initial state = {last_button_state} (1 = uvolněno)")

    # výchozí barva na pásku i potíku
    with rgb_lock:
        r, g, b = rgb["r"], rgb["g"], rgb["b"]
    now_dt = datetime.datetime.now(TZ)
    strip.show_single_led_for_hour(now_dt, r, g, b)
    pot.set_led_color(r, g, b)

    last_minute = None

    while True:
        now_dt = datetime.datetime.now(TZ)

        # titulní režim: jedna LED podle hodiny + refresh času na displeji po minutě
        if not config_mode:
            with rgb_lock:
                r, g, b = rgb["r"], rgb["g"], rgb["b"]
            strip.show_single_led_for_hour(now_dt, r, g, b)

            if last_minute is None or now_dt.minute != last_minute:
                last_minute = now_dt.minute
                print(f"[TIME] MINUTA -> {last_minute}, refresh e-paper (čas)")
                epaper.refresh_time()

        # tlačítko – hrana HIGH->LOW
        cur = GPIO.input(BUTTON_PIN)
        if cur != last_button_state:
            print("Tlačítko =", cur)
            if cur == GPIO.LOW:
                print("[BTN] STISK")
                handle_button_press(epaper, pot, strip)
            else:
                print("[BTN] UVOLNĚNÍ")
            last_button_state = cur

        # PIR – zaznamenáme změny stavu.
        # Třída PirSensor si pamatuje poslední stav sama a při změně vypíše do konzole.
        pir.poll()


        # config režim – stabilní hodnota po 1s
        if config_mode and config_channel is not None:
            val = pot.read_value_0_255()
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

                strip.show_single_led_for_hour(
                    datetime.datetime.now(TZ), r, g, b
                )

                if config_channel == "r":
                    pot.set_led_color(val, 0, 0)
                elif config_channel == "g":
                    pot.set_led_color(0, val, 0)
                elif config_channel == "b":
                    pot.set_led_color(0, 0, val)

                epaper.refresh_config(config_channel, val)

        time.sleep(0.02)


def main():
    sync_time_at_start()

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    strip = LedStrip()
    pot = RGBPot()
    epaper = EpaperDisplay()
    pir = PirSensor()  # použije výchozí PIR_PIN z configu

    strip.selftest()

    try:
        main_loop(epaper, pot, strip, pir)
    except KeyboardInterrupt:
        print("Ukončuji...")
    finally:
        strip.clear()
        GPIO.cleanup()
        epaper.sleep()
        print("Hotovo.")


if __name__ == "__main__":
    main()
