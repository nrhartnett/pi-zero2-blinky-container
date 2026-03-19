# pi-zero2-blinky-container

# Running GPIO-Accessed Python Scripts in Docker on Raspberry Pi

This guide walks through installing Docker on a Raspberry Pi running Raspberry Pi OS Lite, understanding how containers can reach into host hardware, and running a working example that pulses the onboard ACT LED using software PWM. It then covers how the same pattern extends to physical GPIO-connected devices.

---

## Prerequisites

- Raspberry Pi (tested on Pi Zero 2W) running Raspberry Pi OS Lite
- SSH access or a keyboard/monitor connected
- Internet connection on the Pi

---

## Part 1: Installing Docker

### Update the System

```bash
sudo apt update && sudo apt upgrade -y
```

### Install Docker Using the Official Script

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### Add Your User to the Docker Group

This allows you to run Docker commands without prefixing every command with `sudo`.

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Enable Docker on Boot

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

### Verify the Installation

```bash
docker --version
docker run hello-world
```

If the hello-world container runs and prints a confirmation message, Docker is installed correctly.

---

## Part 2: How Containers Access Host Hardware

By default, Docker containers are isolated from the host system. They cannot see the host filesystem, devices, or kernel interfaces unless you explicitly pass them through at runtime.

On a Raspberry Pi, hardware like GPIO pins, I2C buses, and LEDs are exposed through two mechanisms:

- `/dev/` device nodes (e.g. `/dev/gpiomem`, `/dev/i2c-1`)
- `/sys/` virtual filesystem entries (e.g. `/sys/class/leds`, `/sys/class/gpio`)

You pass these into a container using the `-v` flag for sysfs paths and the `--device` flag for device nodes. This is the key principle: you are explicitly declaring which slices of the host hardware the container is allowed to touch. Nothing else is exposed.

### The Symlink Problem

`/sys/class/leds` and `/sys/class/gpio` are symlinks, not real directories. If you mount a symlink into a container, the kernel still treats the underlying sysfs node as read-only. You must resolve the real path first and mount that instead.

```bash
readlink -f /sys/class/leds/ACT
```

This will return the actual device path, something like:

```
/sys/devices/platform/leds/leds/ACT
```

Mount that resolved path and the kernel will allow read/write access from inside the container.

---

## Part 3: The Blinky Example

This example pulses the onboard green ACT LED using software PWM. No wiring is required. It demonstrates the full container-to-host hardware communication pattern using only filesystem writes.

### Project Structure

```
pi-zero2-blinky/
├── Dockerfile
└── blinky.py
```

### blinky.py

```python
import time

LED_PATH = "/sys/class/leds/ACT"

def set_brightness(value: int):
    with open(f"{LED_PATH}/brightness", "w") as f:
        f.write(str(value))

def disable_trigger():
    with open(f"{LED_PATH}/trigger", "w") as f:
        f.write("none")

def restore_trigger():
    with open(f"{LED_PATH}/trigger", "w") as f:
        f.write("mmc0")

def pwm_pulse(duty_cycle: float, frequency: float, duration: float):
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

        print("Running PWM sweep...")
        for duty in [0.1, 0.5, 0.9, 0.5, 0.1]:
            pwm_pulse(duty_cycle=duty, frequency=3.0, duration=2.0)

    finally:
        set_brightness(0)
        restore_trigger()
        print("LED returned to OS control.")
```

### Dockerfile

```dockerfile
FROM alpine:3.19

RUN apk add --no-cache python3

WORKDIR /app
COPY blinky.py .

CMD ["python3", "blinky.py"]
```

Alpine Linux is used here instead of the standard Python image because this script has no external dependencies. The resulting image is roughly 25MB compared to ~150MB for `python:3.11-slim`.

### Build the Image

```bash
docker build -t blinky .
```

### Find the Real LED Path

```bash
readlink -f /sys/class/leds/ACT
```

### Run the Container

```bash
docker run --rm \
  --user root \
  -v /sys/devices/platform/leds/leds/ACT:/sys/class/leds/ACT:rw \
  blinky
```

The ACT LED will begin pulsing. When the script finishes, the LED is returned to OS control automatically via the `finally` block.

---

## Part 4: Extending This Pattern to GPIO-Pinned Devices

The blinky example uses the sysfs LED interface, but the exact same principle applies to any hardware you wire to the GPIO header. The only things that change are which paths and device nodes you mount into the container.

### Using /dev/gpiomem with RPi.GPIO or gpiozero

For Python libraries like `RPi.GPIO` and `gpiozero`, the primary device node needed is `/dev/gpiomem`. This gives userspace programs access to GPIO registers without requiring full root memory access.

```bash
docker run --rm \
  --device /dev/gpiomem \
  my-gpio-image
```

Your Dockerfile for this case needs the library installed:

```dockerfile
FROM python:3.11-slim

RUN pip install --no-cache-dir RPi.GPIO

WORKDIR /app
COPY script.py .

CMD ["python3", "script.py"]
```

Alpine is not recommended here because `RPi.GPIO` has C extensions that do not have prebuilt Alpine wheels and will compile from source, which is slow on low-power Pi hardware.

### Wiring Example: External LED on GPIO17

Connect a 330 ohm resistor in series with an LED between GPIO pin 17 (physical pin 11) and a ground pin.

```python
import RPi.GPIO as GPIO
import time

PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.OUT)

pwm = GPIO.PWM(PIN, 100)
pwm.start(0)

try:
    for duty in range(0, 101, 5):
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.05)
    for duty in range(100, -1, -5):
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.05)
finally:
    pwm.stop()
    GPIO.cleanup()
```

Run it with:

```bash
docker run --rm \
  --device /dev/gpiomem \
  my-gpio-image
```

### I2C Sensors (e.g. BME280 Temperature and Humidity)

First enable I2C on the Pi if you have not already:

```bash
sudo raspi-config
# Interface Options -> I2C -> Enable
```

Wire your sensor to the I2C pins (SDA on GPIO2, SCL on GPIO3) and pass just the I2C device node:

```bash
docker run --rm \
  --device /dev/i2c-1 \
  my-sensor-image
```

### UART Serial Devices

For anything connected over serial (GPS modules, microcontrollers, RS485 adapters):

```bash
docker run --rm \
  --device /dev/ttyAMA0 \
  my-serial-image
```

### Combining Multiple Devices

You can pass as many device nodes and volume mounts as needed. Each one is an explicit, auditable declaration of what the container can touch:

```bash
docker run --rm \
  --device /dev/gpiomem \
  --device /dev/i2c-1 \
  -v /sys/devices/platform/leds/leds/ACT:/sys/class/leds/ACT:rw \
  my-image
```

---

## Part 5: Guard Rails and Isolation

This pattern gives you meaningful hardware isolation without `--privileged` mode. The table below summarizes what is and is not exposed in a typical GPIO container.

| Exposed | Not Exposed |
|---|---|
| Specific device nodes you declare | All other /dev entries |
| Specific sysfs paths you mount | The full /sys tree |
| Read/write access where specified | Host filesystem |
| Named hardware interface only | Host network (unless --network host is set) |
| Nothing else | Host process list |

The key rule is: if it is not in the `docker run` command, the container cannot reach it.

---

## Troubleshooting

**OSError: Read-only file system on a /sys path**
Mount the resolved real path from `readlink -f` rather than the symlink path under `/sys/class`.

**Permission denied on /dev/gpiomem**
Run the container with `--user root` or ensure the host user is in the `gpio` group: `sudo usermod -aG gpio $USER`.

**Package compile errors on Alpine**
Switch to `python:3.11-slim` as your base image for any package that includes C extensions.

**LED not returning to normal after script crash**
The `finally` block in the script handles cleanup on normal exit and on most exceptions. If the container is killed with `SIGKILL` (`docker kill`), the finally block will not run. Restore manually with:

```bash
echo mmc0 | sudo tee /sys/class/leds/ACT/trigger
```