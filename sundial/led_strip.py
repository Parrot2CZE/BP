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
            800000,
            LED_DMA,
            False,
            LED_BRIGHTNESS,
            LED_CHANNEL
        )
        self.strip.begin()

    def clear(self):
        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(0, 0, 0))
        self.strip.show()

    def set_color(self, r, g, b):
        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(r, g, b))
        self.strip.show()

    def selftest(self):
        print("LED selftest: R -> G -> B")
        for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
            for i in range(TOTAL_LED_COUNT):
                self.strip.setPixelColor(i, Color(*color))
            self.strip.show()
            time.sleep(0.5)
        self.clear()

    def show_single_led_for_hour(self, dt, r, g, b):
        """
        Zobrazí jednu LED podle času v 30min krocích.
        Přepínání probíhá v x:15 a x:45.

        Používá LED ACTIVE_LED_START .. ACTIVE_LED_END.
        To musí být přesně 24 LED pro 12 hodin po půlhodinách.
        """
        active_count = ACTIVE_LED_END - ACTIVE_LED_START + 1
        if active_count != 24:
            raise ValueError(
                f"Aktivní rozsah LED musí mít 24 pozic, aktuálně má {active_count}"
            )

        hour_12 = dt.hour % 12
        minute = dt.minute

        if minute < 15:
            slot_hour = (hour_12 - 1) % 12
            half = 1
        elif minute < 45:
            slot_hour = hour_12 % 12
            half = 0
        else:
            slot_hour = hour_12 % 12
            half = 1

        slot = slot_hour * 2 + half
        led_idx = ACTIVE_LED_START + slot

        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(0, 0, 0))

        if 0 <= led_idx < TOTAL_LED_COUNT:
            self.strip.setPixelColor(led_idx, Color(r, g, b))

        self.strip.show()