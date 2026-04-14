#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import datetime
import threading

import RPi.GPIO as GPIO

from .controller import SundialController
from .webapp import create_app

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
pir_active = None          # stav podle PIR
last_pot_led_rgb = None

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

def enter_config_mode(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip, controller: SundialController):
    global config_mode, config_channel
    config_mode = True
    config_channel = "r"
    print("=== VSTUP DO REŽIMU NASTAVENÍ BARVY (R) ===")

    val, _, _ = controller.get_rgb()

    _reset_pot_tracking(val)
    pot.set_led_color(val, 0, 0)
    epaper.refresh_config("r", val)


def advance_config_channel(epaper: EpaperDisplay, pot: RGBPot, controller: SundialController):
    global config_channel

    if config_channel == "r":
        config_channel = "g"
        print("PŘEPÍNÁM NA G")
        _, val, _ = controller.get_rgb()
        _reset_pot_tracking(val)
        pot.set_led_color(0, val, 0)
        epaper.refresh_config("g", val)

    elif config_channel == "g":
        config_channel = "b"
        print("PŘEPÍNÁM NA B")
        _, _, val = controller.get_rgb()
        _reset_pot_tracking(val)
        pot.set_led_color(0, 0, val)
        epaper.refresh_config("b", val)

    elif config_channel == "b":
        exit_config_mode(epaper, pot, controller)


def exit_config_mode(epaper: EpaperDisplay, pot: RGBPot, controller: SundialController):
    global config_mode, config_channel
    config_mode = False
    config_channel = None
    print("=== KONEC NASTAVOVÁNÍ BARVY ===")

    r, g, b = controller.get_rgb()

    pot.set_led_color(r, g, b)

    # displej zpět na čas
    epaper.refresh_time()


def handle_button_press(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip, controller: SundialController):
    if not config_mode:
        print("[BTN] klik mimo config -> enter_config_mode()")
        enter_config_mode(epaper, pot, strip, controller)
    else:
        print("[BTN] klik v config -> advance_config_channel()")
        advance_config_channel(epaper, pot, controller)


# ---------- hlavní smyčka ----------

def main_loop(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip, pir: PirSensor, controller: SundialController):
    global last_button_state, pot_raw_last, pot_displayed_val, pot_last_change_time, pir_active, last_pot_led_rgb

    last_button_state = GPIO.input(BUTTON_PIN)
    print(f"[INIT] BUTTON initial state = {last_button_state} (1 = uvolněno)")

    # výchozí barva
    r, g, b = controller.get_rgb()

    # počáteční stav PIR
    pir_state = pir.poll()
    pir_active = (pir_state == GPIO.HIGH)

    if pir_active:
        now_dt = datetime.datetime.now(TZ)
        strip.show_single_led_for_hour(now_dt, r, g, b)
        pot.set_led_color(r, g, b)
        last_pot_led_rgb = (r, g, b)
        print("[PIR] Při startu detekován pohyb -> hodiny AKTIVNÍ")
    else:
        strip.clear()
        pot.set_led_color(0, 0, 0)
        last_pot_led_rgb = (0, 0, 0)
        print("[PIR] Při startu bez pohybu -> hodiny ZHASNUTÉ")

    last_minute = None

    while True:
        now_dt = datetime.datetime.now(TZ)

        # PIR – aktuální stav přítomnosti
        enabled = controller.is_enabled()
        use_pir = controller.is_pir_enabled()
        r, g, b = controller.get_rgb()

        # Synchronizace LED v potenciometru při změně RGB z webu
        if pir_active and not config_mode:
            desired_pot_rgb = (r, g, b)
        else:
            desired_pot_rgb = None

        if desired_pot_rgb is not None and desired_pot_rgb != last_pot_led_rgb:
            pot.set_led_color(*desired_pot_rgb)
            last_pot_led_rgb = desired_pot_rgb

        pir_state = pir.poll()
        motion_detected = (pir_state == GPIO.HIGH)
        controller.set_motion(motion_detected)

        if not enabled:
            current_active = False
        elif use_pir:
            current_active = motion_detected
        else:
            current_active = True

        # změna stavu podle PIR / webu
        if current_active != pir_active:
            pir_active = current_active

            if pir_active:
                print("[PIR] Aktivace hodin")
                strip.show_single_led_for_hour(now_dt, r, g, b)
                pot.set_led_color(r, g, b)
                last_pot_led_rgb = (r, g, b)

                if config_mode and config_channel is not None:
                    if config_channel == "r":
                        val, _, _ = controller.get_rgb()
                    elif config_channel == "g":
                        _, val, _ = controller.get_rgb()
                    elif config_channel == "b":
                        _, _, val = controller.get_rgb()
                    else:
                        val = 0

                    epaper.refresh_config(config_channel, val)
                else:
                    epaper.refresh_time()

            else:
                print("[PIR] Deaktivace hodin")
                strip.clear()
                pot.set_led_color(0, 0, 0)
                last_pot_led_rgb = (0, 0, 0)

        # pokud nejsou hodiny aktivní, nic dalšího neděláme
        if not pir_active:
            time.sleep(0.05)
            continue

        # titulní režim: jedna LED podle času + refresh času na displeji po minutě
        if not config_mode:
            r, g, b = controller.get_rgb()
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
                handle_button_press(epaper, pot, strip, controller)
            else:
                print("[BTN] UVOLNĚNÍ")
            last_button_state = cur

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

                cur_r, cur_g, cur_b = controller.get_rgb()

                if config_channel == "r":
                    controller.set_rgb(val, cur_g, cur_b)
                elif config_channel == "g":
                    controller.set_rgb(cur_r, val, cur_b)
                elif config_channel == "b":
                    controller.set_rgb(cur_r, cur_g, val)

                r, g, b = controller.get_rgb()
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
    controller = SundialController()
    app = create_app(controller)
    web_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    web_thread.start()
    print("[WEB] Web běží na http://0.0.0.0:5000")

    strip.selftest()

    try:
        main_loop(epaper, pot, strip, pir, controller)
    except KeyboardInterrupt:
        print("Ukončuji...")
    finally:
        strip.clear()
        GPIO.cleanup()
        epaper.sleep()
        print("Hotovo.")


if __name__ == "__main__":
    main()
