import time
import os

LED_PATH = "/sys/class/leds/ACT"  # or "led0" on older Pi OS versions

def set_brightness(value: int):
    """0 = off, 1 = on"""
    with open(f"{LED_PATH}/brightness", "w") as f:
        f.write(str(value))

def disable_trigger():
    """Release the LED from the OS (heartbeat/mmc activity)"""
    with open(f"{LED_PATH}/trigger", "w") as f:
        f.write("none")

def restore_trigger():
    """Give the LED back to the OS on exit"""
    with open(f"{LED_PATH}/trigger", "w") as f:
        f.write("mmc0")  # Default: flash on SD card activity

def pwm_pulse(duty_cycle: float, frequency: float, duration: float):
    """
    Software PWM via filesystem writes.
    duty_cycle: 0.0 to 1.0
    frequency:  Hz
    duration:   seconds to run
    """
    period = 1.0 / frequency
    on_time = period * duty_cycle
    off_time = period * (1.0 - duty_cycle)
    end = time.time() + duration

    while time.time() < end:
        set_brightness(1)
        time.sleep(on_time)
        set_brightness(0)
        time.sleep(off_time)

if __name__ == "__main__":
    disable_trigger()
    try:
        print("Pulsing at 25% duty cycle, 2Hz for 5 seconds...")
        pwm_pulse(duty_cycle=0.25, frequency=2.0, duration=5.0)

        print("Pulsing at 75% duty cycle, 5Hz for 5 seconds...")
        pwm_pulse(duty_cycle=0.75, frequency=5.0, duration=5.0)

        print("SOS in PWM...")
        for duty in [0.1, 0.5, 0.9, 0.5, 0.1]:
            pwm_pulse(duty_cycle=duty, frequency=3.0, duration=2.0)

    finally:
        set_brightness(0)
        restore_trigger()
        print("LED returned to OS control.")