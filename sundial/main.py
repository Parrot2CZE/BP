#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sundial/main.py
===============
Vstupní bod aplikace a hlavní řídicí smyčka.

Architektura:
  - SundialController  – sdílený stav (RGB, enabled, PIR, pohyb)
  - AzureSync          – synchronizace se vzdáleným API (poll + push ve vláknech)
  - LedStrip           – WS281x LED pásek (24 LED, 12 hodin × 2 půlhodiny)
  - RGBPot             – RGB potenciometr (IO expander PIM523)
  - EpaperDisplay      – e-ink displej 2.13" (čas / config screen)
  - PirSensor          – HC-SR501 pohybový senzor
  - Tlačítko (GPIO)    – vstup do config režimu + přepínání R/G/B kanálů

Lokální Flask web byl záměrně odstraněn – ovládání probíhá výhradně
přes Azure Functions + static frontend (sundial-azure/).
"""

import time
import datetime
import threading

import RPi.GPIO as GPIO

from .controller import SundialController
from .azure_sync import AzureSync

from .config import TZ, BUTTON_PIN
from .led_strip import LedStrip
from .rgb_pot import RGBPot
from .epaper_display import EpaperDisplay
from .time_sync import sync_time_at_start
from .pir_sensor import PirSensor


# ──────────────────────────────────────────────
# Globální stav config režimu
# (config režim = fyzické nastavení RGB přes potenciometr)
# ──────────────────────────────────────────────

config_mode    = False   # True = probíhá nastavování barvy tlačítkem + potíkem
config_channel = None    # aktuálně nastavovaný kanál: "r" / "g" / "b"
last_button_state = 1    # GPIO pull-up → klidový stav je 1

# Pamatujeme si, jakou barvu jsme naposledy poslali do LED v potíku,
# abychom zbytečně nepřepisovali stejnou hodnotu.
last_pot_led_rgb = None

# ──────────────────────────────────────────────
# Sledování potenciometru (anti-jitter + stabilizace)
# ──────────────────────────────────────────────

pot_raw_last        = None   # poslední surová hodnota z ADC
pot_displayed_val   = None   # hodnota naposledy zobrazená / uložená
pot_last_change_time = 0.0   # monotonic timestamp poslední změny

POT_STABLE_SEC = 1.0   # jak dlouho musí být hodnota stabilní, než ji přijmeme
POT_JITTER_TOL = 3     # o kolik se smí pohybovat ADC bez toho, aby se to počítalo jako změna


def _reset_pot_tracking(initial_val: int):
    """Resetuje sledování potenciometru na danou počáteční hodnotu.
    Voláme při vstupu do config kanálu, aby se předchozí pozice nebrala jako změna."""
    global pot_raw_last, pot_displayed_val, pot_last_change_time
    pot_raw_last         = initial_val
    pot_displayed_val    = initial_val
    pot_last_change_time = time.monotonic()


# ──────────────────────────────────────────────
# Config režim – vstup / přepínání kanálů / výstup
# ──────────────────────────────────────────────

def enter_config_mode(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip,
                      controller: SundialController, azure_sync: AzureSync):
    """
    Vstoupí do config režimu na kanálu R.
    AzureSync dostane příznak, aby nepřepisoval RGB z cloudu,
    dokud uživatel fyzicky nastavuje hodnotu.
    """
    global config_mode, config_channel
    config_mode    = True
    config_channel = "r"
    azure_sync.set_config_mode(True)
    print("=== VSTUP DO REŽIMU NASTAVENÍ BARVY (R) ===")

    val, _, _ = controller.get_rgb()
    _reset_pot_tracking(val)
    pot.set_led_color(val, 0, 0)   # potík svítí čistě červeně jako indikace
    epaper.refresh_config("r", val)


def advance_config_channel(epaper: EpaperDisplay, pot: RGBPot,
                           controller: SundialController, azure_sync: AzureSync):
    """
    Přepne na další kanál (R → G → B → exit).
    Při každém přepnutí se potenciometr nastaví na aktuální hodnotu daného kanálu,
    takže první pohyb vždy vychází ze skutečné hodnoty, ne z nuly.
    """
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
        # poslední kanál → ukončení config režimu
        exit_config_mode(epaper, pot, controller, azure_sync)


def exit_config_mode(epaper: EpaperDisplay, pot: RGBPot,
                     controller: SundialController, azure_sync: AzureSync):
    """
    Ukončí config režim:
      - potík se vrátí na výslednou barvu
      - nová barva se okamžitě pushne do Azure
      - displej zobrazí zpět čas
    """
    global config_mode, config_channel
    config_mode    = False
    config_channel = None
    azure_sync.set_config_mode(False)
    print("=== KONEC NASTAVOVÁNÍ BARVY ===")

    r, g, b = controller.get_rgb()
    pot.set_led_color(r, g, b)
    azure_sync.push_rgb_now()   # push mimo pravidelný interval, aby se změna neztratila
    epaper.refresh_time()


def handle_button_press(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip,
                        controller: SundialController, azure_sync: AzureSync):
    """Obsluha stisku tlačítka: mimo config → vstup, uvnitř config → další kanál."""
    if not config_mode:
        print("[BTN] klik mimo config -> enter_config_mode()")
        enter_config_mode(epaper, pot, strip, controller, azure_sync)
    else:
        print("[BTN] klik v config -> advance_config_channel()")
        advance_config_channel(epaper, pot, controller, azure_sync)


# ──────────────────────────────────────────────
# Hlavní smyčka (~50 Hz, tj. iterace každých ~20 ms)
# ──────────────────────────────────────────────

def main_loop(epaper: EpaperDisplay, pot: RGBPot, strip: LedStrip, pir: PirSensor,
              controller: SundialController, azure_sync: AzureSync):
    global last_button_state, pot_raw_last, pot_displayed_val, pot_last_change_time
    global pir_active, last_pot_led_rgb

    last_button_state = GPIO.input(BUTTON_PIN)
    print(f"[INIT] BUTTON initial state = {last_button_state} (1 = uvolněno)")

    # ── počáteční stav ──
    r, g, b = controller.get_rgb()
    pir_state  = pir.poll()
    pir_active = (pir_state == GPIO.HIGH)

    if pir_active:
        now_dt = datetime.datetime.now(TZ)
        strip.show_single_led_for_hour(now_dt, r, g, b)
        pot.set_led_color(r, g, b)
        last_pot_led_rgb = (r, g, b)
        print("[PIR] Při startu detekován pohyb → hodiny AKTIVNÍ")
    else:
        strip.clear()
        pot.set_led_color(0, 0, 0)
        last_pot_led_rgb = (0, 0, 0)
        print("[PIR] Při startu bez pohybu → hodiny ZHASNUTÉ")

    last_minute = None

    while True:
        # ── Azure sync tick (nevyblokuje – HTTP jede ve vlastním vlákně) ──
        azure_sync.tick()

        now_dt  = datetime.datetime.now(TZ)
        enabled = controller.is_enabled()
        use_pir = controller.is_pir_enabled()
        r, g, b = controller.get_rgb()

        # ── Synchronizace barvy LED v potíku při změně RGB z webu ──
        # (jen když svítíme a nejsme v config režimu)
        if pir_active and not config_mode:
            desired_pot_rgb = (r, g, b)
            if desired_pot_rgb != last_pot_led_rgb:
                pot.set_led_color(*desired_pot_rgb)
                last_pot_led_rgb = desired_pot_rgb

        # ── PIR / enabled / use_pir → rozhodnutí, zda hodiny svítí ──
        motion_detected = (pir.poll() == GPIO.HIGH)
        controller.set_motion(motion_detected)

        if not enabled:
            current_active = False          # vypnuto z webu
        elif use_pir:
            current_active = motion_detected  # řídí PIR
        else:
            current_active = True           # vždy svítí (PIR přemostěn)

        # ── Reakce na změnu stavu aktivace hodin ──
        if current_active != pir_active:
            pir_active = current_active

            if pir_active:
                print("[PIR] Aktivace hodin")
                strip.show_single_led_for_hour(now_dt, r, g, b)
                pot.set_led_color(r, g, b)
                last_pot_led_rgb = (r, g, b)
                # obnov displej (config screen nebo čas)
                if config_mode and config_channel:
                    ch_vals = {"r": r, "g": g, "b": b}
                    epaper.refresh_config(config_channel, ch_vals[config_channel])
                else:
                    epaper.refresh_time()
            else:
                print("[PIR] Deaktivace hodin")
                strip.clear()
                pot.set_led_color(0, 0, 0)
                last_pot_led_rgb = (0, 0, 0)

        # ── Pokud hodiny nesví, zbytek smyčky přeskočíme ──
        if not pir_active:
            time.sleep(0.05)
            continue

        # ── Normální (non-config) provoz: LED sleduje čas, displej jednou za minutu ──
        if not config_mode:
            strip.show_single_led_for_hour(now_dt, r, g, b)

            if last_minute is None or now_dt.minute != last_minute:
                last_minute = now_dt.minute
                print(f"[TIME] MINUTA → {last_minute}, refresh e-paper")
                epaper.refresh_time()

        # ── Tlačítko: detekce sestupné hrany (HIGH → LOW) ──
        cur = GPIO.input(BUTTON_PIN)
        if cur != last_button_state:
            if cur == GPIO.LOW:
                print("[BTN] STISK")
                handle_button_press(epaper, pot, strip, controller, azure_sync)
            else:
                print("[BTN] UVOLNĚNÍ")
            last_button_state = cur

        # ── Config režim: přečti potenciometr a po POT_STABLE_SEC stabilní hodnoty ulož ──
        if config_mode and config_channel:
            val      = pot.read_value_0_255()
            now_mono = time.monotonic()

            if pot_raw_last is None:
                _reset_pot_tracking(val)

            # pohyb nad prahem jitteru → resetuj čekací čas
            if abs(val - pot_raw_last) > POT_JITTER_TOL:
                pot_raw_last         = val
                pot_last_change_time = now_mono

            # hodnota se stabilizovala → ulož ji
            if (now_mono - pot_last_change_time) >= POT_STABLE_SEC and val != pot_displayed_val:
                pot_displayed_val = val
                print(f"[POT] STABILNÍ hodnota {config_channel.upper()} = {val}")

                cur_r, cur_g, cur_b = controller.get_rgb()
                if config_channel == "r":
                    controller.set_rgb(val,   cur_g, cur_b)
                    pot.set_led_color(val, 0, 0)
                elif config_channel == "g":
                    controller.set_rgb(cur_r, val,   cur_b)
                    pot.set_led_color(0, val, 0)
                elif config_channel == "b":
                    controller.set_rgb(cur_r, cur_g, val)
                    pot.set_led_color(0, 0, val)

                r, g, b = controller.get_rgb()
                strip.show_single_led_for_hour(datetime.datetime.now(TZ), r, g, b)
                epaper.refresh_config(config_channel, val)

        time.sleep(0.02)   # ~50 Hz


# ──────────────────────────────────────────────
# Inicializace a spuštění
# ──────────────────────────────────────────────

def main():
    # Nejdřív synchronizuj systémový čas přes timeapi.io
    sync_time_at_start()

    # GPIO setup – tlačítko s interním pull-up
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Inicializace hardware modulů
    strip      = LedStrip()
    pot        = RGBPot()
    epaper     = EpaperDisplay()
    pir        = PirSensor()
    controller = SundialController()
    azure_sync = AzureSync(controller)

    # Krátký selftest LED pásku (R → G → B)
    strip.selftest()

    try:
        main_loop(epaper, pot, strip, pir, controller, azure_sync)
    except KeyboardInterrupt:
        print("Ukončuji...")
    finally:
        # Čistý shutdown: zhasni LED, uvolni GPIO, uspí displej
        strip.clear()
        GPIO.cleanup()
        epaper.sleep()
        print("Hotovo.")


if __name__ == "__main__":
    main()
