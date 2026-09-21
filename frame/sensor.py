from __future__ import annotations

import glob
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import serial
from serial.tools import list_ports

from frame.constants import BAUD_RATE, USB_PORT_HINTS
from frame.matrix import DepthFrame, pop_usb_frames


def candidate_serial_ports() -> list[str]:
    found: list[str] = []
    for port in list_ports.comports():
        blob = f"{port.device} {port.description} {port.hwid}".lower()
        if any(hint.lower() in blob for hint in USB_PORT_HINTS):
            found.append(port.device)
        elif "2e8a" in blob:  # Raspberry Pi / RP2040 USB vendor
            found.append(port.device)
    patterns = (
        "/dev/cu.usbmodem*",
        "/dev/cu.usbserial*",
        "/dev/tty.usbmodem*",
        "/dev/ttyACM*",
        "/dev/ttyUSB*",
    )
    for pattern in patterns:
        for path in glob.glob(pattern):
            if path not in found:
                found.append(path)
    # Prefer cu.* over tty.* on macOS.
    found.sort(key=lambda p: (0 if Path(p).name.startswith("cu.") else 1, p))
    return found


def describe_serial_ports() -> str:
    ports = list(list_ports.comports())
    if not ports:
        return "No serial devices enumerated."
    lines = []
    for port in ports:
        lines.append(f"  {port.device}  {port.description}  [{port.hwid}]")
    return "\n".join(lines)


class UsbMatrixSensor:
    """Reads the SEN0628 USB-C CDC stream. Same path works on Mac and Pi."""

    def __init__(self, port: str, baud: int = BAUD_RATE, timeout: float = 0.2) -> None:
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._buffer = ""

    def open(self) -> None:
        self._serial = serial.Serial(self.port, self.baud, timeout=self.timeout)
        self._serial.reset_input_buffer()
        self._buffer = ""

    def close(self) -> None:
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def __enter__(self) -> UsbMatrixSensor:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def read_chunk(self) -> str:
        if self._serial is None:
            raise RuntimeError("sensor is not open")
        data = self._serial.read(self._serial.in_waiting or 1)
        if not data:
            return ""
        return data.decode("utf-8", errors="replace")

    def frames(self) -> Iterator[DepthFrame]:
        if self._serial is None:
            raise RuntimeError("sensor is not open")
        while True:
            self._buffer += self.read_chunk()
            ready, self._buffer = pop_usb_frames(self._buffer)
            for frame in ready:
                yield frame


def wait_for_port(timeout_seconds: float | None = None) -> str:
    started = time.monotonic()
    while True:
        ports = candidate_serial_ports()
        if ports:
            return ports[0]
        if timeout_seconds is not None and time.monotonic() - started > timeout_seconds:
            raise TimeoutError("SEN0628 serial port did not appear")
        time.sleep(0.4)


def main_probe() -> int:
    print("Serial ports:")
    print(describe_serial_ports())
    candidates = candidate_serial_ports()
    print("SEN0628 candidates:", candidates or "(none)")
    return 0 if candidates else 1


if __name__ == "__main__":
    sys.exit(main_probe())
