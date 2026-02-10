import ioexpander as io
from .config import (
    I2C_ADDR, POT_VREF,
    PIN_RED, PIN_GREEN, PIN_BLUE,
    POT_ENC_A, POT_ENC_B, POT_ENC_C,
    PWM_PERIOD
)

# SMBUS fallback – stejně jako v původním souboru
try:
    import smbus  # noqa: F401
except ImportError:
    import smbus2 as smbus
    import sys as _sys
    _sys.modules["smbus"] = smbus


class RGBPot:
    def __init__(self):
        self.ioe = None
        self._init_ioe()

    def _init_ioe(self):
        try:
            self.ioe = io.IOE(i2c_addr=I2C_ADDR)
            self.ioe.set_adc_vref(POT_VREF)

            # potenciometr – stejně jako v původním kódu
            self.ioe.set_mode(POT_ENC_A, io.PIN_MODE_PP)
            self.ioe.set_mode(POT_ENC_B, io.PIN_MODE_PP)
            self.ioe.set_mode(POT_ENC_C, io.ADC)

            self.ioe.output(POT_ENC_A, 1)
            self.ioe.output(POT_ENC_B, 0)

            # PWM pro RGB LED v knoflíku
            self.ioe.set_pwm_period(PWM_PERIOD)
            self.ioe.set_pwm_control(divider=2)

            self.ioe.set_mode(PIN_RED, io.PWM, invert=True)
            self.ioe.set_mode(PIN_GREEN, io.PWM, invert=True)
            self.ioe.set_mode(PIN_BLUE, io.PWM, invert=True)

            print("RGB potenciometr inicializován.")
        except Exception as e:
            print("RGB pot init fail:", repr(e))
            self.ioe = None

    def read_value_0_255(self) -> int:
        """Vrátí hodnotu potenciometru 0–255 z POT_ENC_C (pin 11)."""
        if self.ioe is None:
            return 0
        try:
            v = self.ioe.input(POT_ENC_C)  # v Voltech
        except Exception as e:
            print("read_value_0_255: chyba při čtení ADC:", repr(e))
            return 0

        if v < 0:
            v = 0
        if v > POT_VREF:
            v = POT_VREF

        return int(round((v / POT_VREF) * 255))

    def _scale_255_to_pwm(self, v: int) -> int:
        v = max(0, min(255, int(v)))
        return int(v * PWM_PERIOD / 255)

    def set_led_color(self, r: int, g: int, b: int):
        """Nastaví barvu LED v potenciometru (0–255)."""
        if self.ioe is None:
            return
        try:
            self.ioe.output(PIN_RED, self._scale_255_to_pwm(r))
            self.ioe.output(PIN_GREEN, self._scale_255_to_pwm(g))
            self.ioe.output(PIN_BLUE, self._scale_255_to_pwm(b))
        except Exception as e:
            print("set_led_color: chyba:", repr(e))
