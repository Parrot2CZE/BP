"""
sundial/led_strip.py
====================
Ovládání WS281x LED pásku.

Mapování 24 LED → 12 hodin (každá hodina = 2 půlhodiny):
  - slot 0  = 12:15–12:44  (první půlhodina hodiny 12)
  - slot 1  = 12:45–01:14  (druhá půlhodina hodiny 12)
  - slot 2  = 01:15–01:44  (první půlhodina hodiny 1)
  - …atd.

Přesná logika přepínání:
  minuta < 15  → svítí druhá půlhodina předchozí hodiny (přetečení přes půlnoc ošetřeno mod 12)
  minuta 15–44 → svítí první půlhodina aktuální hodiny
  minuta ≥ 45  → svítí druhá půlhodina aktuální hodiny
"""

import time
from rpi_ws281x import PixelStrip, Color

from .config import (
    TOTAL_LED_COUNT,
    LED_PIN,
    LED_BRIGHTNESS,
    LED_DMA,
    LED_CHANNEL,
    ACTIVE_LED_START,
    ACTIVE_LED_END,
)


class LedStrip:
    def __init__(self):
        self.strip = PixelStrip(
            TOTAL_LED_COUNT,
            LED_PIN,
            800000,      # datová frekvence 800 kHz
            LED_DMA,
            False,       # invert signal
            LED_BRIGHTNESS,
            LED_CHANNEL
        )
        self.strip.begin()

    def clear(self):
        """Zhasne všechny LED."""
        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(0, 0, 0))
        self.strip.show()

    def set_color(self, r: int, g: int, b: int):
        """Rozsvítí všechny LED zadanou barvou (používá se jen pro selftest)."""
        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(r, g, b))
        self.strip.show()

    def selftest(self):
        """Krátký vizuální test při startu: R → G → B, 0.5 s každá barva."""
        print("LED selftest: R → G → B")
        for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
            self.set_color(*color)
            time.sleep(0.5)
        self.clear()

    def show_single_led_for_hour(self, dt, r: int, g: int, b: int):
        """
        Rozsvítí jednu LED odpovídající aktuálnímu časo-slotu, ostatní zhasne.

        Aktivní rozsah musí mít přesně 24 pozic (ACTIVE_LED_START … ACTIVE_LED_END).
        """
        active_count = ACTIVE_LED_END - ACTIVE_LED_START + 1
        if active_count != 24:
            raise ValueError(
                f"Aktivní rozsah LED musí mít 24 pozic, aktuálně má {active_count}"
            )

        hour_12 = dt.hour % 12   # 0–11 (0 = 12:xx)
        minute  = dt.minute

        # Určení slotu podle minuty
        if minute < 15:
            # Jsme těsně po celé hodině → zobrazujeme konec předchozí hodiny
            slot_hour = (hour_12 - 1) % 12
            half = 1   # druhá půlhodina
        elif minute < 45:
            # Střed hodiny → první půlhodina
            slot_hour = hour_12 % 12
            half = 0
        else:
            # Konec hodiny → druhá půlhodina
            slot_hour = hour_12 % 12
            half = 1

        slot    = slot_hour * 2 + half
        led_idx = ACTIVE_LED_START + slot

        # Zhasni vše, pak rozsvítí jeden pixel
        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(0, 0, 0))

        if 0 <= led_idx < TOTAL_LED_COUNT:
            self.strip.setPixelColor(led_idx, Color(r, g, b))

        self.strip.show()
