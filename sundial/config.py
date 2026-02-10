from zoneinfo import ZoneInfo
import pathlib

# Časová zóna
TZ = ZoneInfo("Europe/Prague")

# LED pásek
TOTAL_LED_COUNT = 15          # počet FUNKČNÍCH LED
LED_PIN = 18                  # GPIO18 (pin 12)
LED_BRIGHTNESS = 128
LED_DMA = 10
LED_CHANNEL = 0

# Tlačítko
BUTTON_PIN = 20               # GPIO20 = pin 38, druhá noha na GND (pin 39)

# PIR pohybový senzor (HC-SR501)
PIR_PIN = 16                  # GPIO16 = pin 36, výstup z HC-SR501

# RGB potenciometr (PIM523)
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

# E-paper / fonty
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BASE_DIR = pathlib.Path(__file__).resolve().parent

# TP_lib pro e-paper
TP_LIB_PATH = "/home/jakub/Touch_e-Paper_Code/python/lib"
