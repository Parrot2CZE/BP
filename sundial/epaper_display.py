import os
import sys
import datetime
from PIL import Image, ImageDraw, ImageFont

from .config import FONT_PATH, TP_LIB_PATH, TZ

# Přidání TP_lib na sys.path (stejně jako v původním souboru)
if os.path.isdir(TP_LIB_PATH):
    sys.path.append(TP_LIB_PATH)
else:
    print("VAROVÁNÍ: Nenalezena cesta k TP_lib:", TP_LIB_PATH)

from TP_lib import epd2in13_V4  # type: ignore


def _load_fonts():
    try:
        font_big = ImageFont.truetype(FONT_PATH, 32)
        font_small = ImageFont.truetype(FONT_PATH, 16)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()
    return font_big, font_small


class EpaperDisplay:
    def __init__(self):
        self.epd = epd2in13_V4.EPD()
        self.epd.init(self.epd.FULL_UPDATE)
        self.epd.Clear(0xFF)

        self.WIDTH, self.HEIGHT = self.epd.height, self.epd.width
        self.image = Image.new("1", (self.WIDTH, self.HEIGHT), 255)
        self.draw = ImageDraw.Draw(self.image)

        self.font_big, self.font_small = _load_fonts()

        # první vykreslení – plný update
        self.draw_time_screen()
        self.epd.display(self.epd.getbuffer(self.image))

        # pak přepneme na partial update
        self.epd.init(self.epd.PART_UPDATE)

    # ---------- veřejné API ----------

    def draw_time_screen(self):
        """Hlavní „titulní“ obrazovka – jen čas uprostřed."""
        self.draw.rectangle((0, 0, self.WIDTH, self.HEIGHT), fill=255)
        now_txt = datetime.datetime.now(TZ).strftime("%H:%M")
        bbox = self.draw.textbbox((0, 0), now_txt, font=self.font_big)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        self.draw.text(
            ((self.WIDTH - w) // 2, (self.HEIGHT - h) // 2),
            now_txt,
            font=self.font_big,
            fill=0,
        )

    def _channel_label(self, ch: str) -> str:
        if ch == "r":
            return "ČERVENÁ"
        if ch == "g":
            return "ZELENÁ"
        if ch == "b":
            return "MODRÁ"
        return "NEZNÁMÁ"

    def draw_config_screen(self, channel: str, value: int):
        """
        Obrazovka při nastavování barvy:
        - název barvy (ČERVENÁ/ZELENÁ/MODRÁ)
        - pod tím číslo 0–255
        """
        self.draw.rectangle((0, 0, self.WIDTH, self.HEIGHT), fill=255)

        label = self._channel_label(channel)

        bbox_label = self.draw.textbbox((0, 0), label, font=self.font_small)
        lw = bbox_label[2] - bbox_label[0]
        self.draw.text(
            ((self.WIDTH - lw) // 2, 10),
            label,
            font=self.font_small,
            fill=0,
        )

        val_txt = str(value)
        bbox_val = self.draw.textbbox((0, 0), val_txt, font=self.font_big)
        vw = bbox_val[2] - bbox_val[0]
        vh = bbox_val[3] - bbox_val[1]
        self.draw.text(
            ((self.WIDTH - vw) // 2, (self.HEIGHT - vh) // 2),
            val_txt,
            font=self.font_big,
            fill=0,
        )

    def refresh_time(self):
        self.draw_time_screen()
        self.epd.displayPartial(self.epd.getbuffer(self.image))

    def refresh_config(self, channel: str, value: int):
        self.draw_config_screen(channel, value)
        self.epd.displayPartial(self.epd.getbuffer(self.image))

    def sleep(self):
        try:
            self.epd.sleep()
        except Exception:
            pass
