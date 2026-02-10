import time
from rpi_ws281x import PixelStrip, Color

from .config import TOTAL_LED_COUNT, LED_PIN, LED_BRIGHTNESS, LED_DMA, LED_CHANNEL


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
        Svítí jen jedna LED podle hodiny.
        12h mapování: 1..12 -> index 0..11.
        Když máš 15 funkčních LED, prvních 12 použijeme pro hodiny.
        """
        h12 = dt.hour % 12
        if h12 == 0:
            h12 = 12
        idx = h12 - 1  # 0..11

        for i in range(TOTAL_LED_COUNT):
            self.strip.setPixelColor(i, Color(0, 0, 0))

        if idx < TOTAL_LED_COUNT:
            self.strip.setPixelColor(idx, Color(r, g, b))

        self.strip.show()