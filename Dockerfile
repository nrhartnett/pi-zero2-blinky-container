FROM python:3.11-slim

WORKDIR /app
COPY blinky.py .

# No pip installs needed — pure stdlib + sysfs
CMD ["python", "blinky.py"]