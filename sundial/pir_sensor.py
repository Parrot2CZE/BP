# pir_sensor.py
import RPi.GPIO as GPIO
from .config import PIR_PIN


class PirSensor:
    """
    Jednoduchý wrapper kolem HC-SR501:
    - nastaví pin jako vstup
    - pamatuje si poslední stav
    - při změně stavu vypíše do konzole (pohyb / konec pohybu)
    """

    def __init__(self, pin: int = PIR_PIN):
        self.pin = pin
        GPIO.setup(self.pin, GPIO.IN)
        self.last_state = GPIO.input(self.pin)
        print(f"[PIR] init na GPIO {self.pin}, initial_state={self.last_state} "
              "(0 = žádný pohyb, 1 = pohyb)")

    def poll(self) -> int:
        """
        Přečte aktuální stav.
        Když se liší od předchozího, vypíše změnu do konzole.
        Vrací 0/1 (GPIO.LOW / GPIO.HIGH).
        """
        state = GPIO.input(self.pin)
        if state != self.last_state:
            if state == GPIO.HIGH:
                print(f"[PIR] DETEKOVÁN POHYB (GPIO {self.pin} = 1)")
            else:
                print(f"[PIR] KONEC POHYBU (GPIO {self.pin} = 0)")
            self.last_state = state
        return state
