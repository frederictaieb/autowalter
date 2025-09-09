from machine import ADC, Pin
import time

# Capteur branché sur GP26 / ADC0
# ADC_DRY  = 44000
# ADC_WET  = 17500

adc = ADC(26)

while True:
    val = adc.read_u16()  # lecture brute 0..65535
    print("Valeur ADC:", val)
    time.sleep(1)

