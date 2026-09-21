from __future__ import annotations

import time
from pathlib import Path

from frame.discover import BOOTSEL_VOLUME, bootsel_mounted

FIRMWARE = Path(__file__).resolve().parents[1] / "firmware" / "SEN0628-V1.3-20250904.uf2"


def wait_for_bootsel(timeout_seconds: float = 60) -> Path:
    started = time.monotonic()
    while not bootsel_mounted():
        if time.monotonic() - started > timeout_seconds:
            raise TimeoutError(
                "RPI-RP2 did not appear. Hold BOOT on the SEN0628, then plug USB-C."
            )
        time.sleep(0.3)
    return BOOTSEL_VOLUME


def flash(firmware: Path = FIRMWARE) -> None:
    if not firmware.is_file():
        raise FileNotFoundError(firmware)
    volume = wait_for_bootsel()
    dest = volume / firmware.name
    print(f"Copying {firmware.name} -> {dest}")
    dest.write_bytes(firmware.read_bytes())
    # The RP2040 reboots as soon as the UF2 lands; Finder/cp I/O errors are normal.
    time.sleep(2)
    print("Flash sent. Unplug/replug if /dev/cu.usbmodem* does not appear.")


def main() -> int:
    print(f"Firmware: {FIRMWARE} ({FIRMWARE.stat().st_size} bytes)")
    print("Hold BOOT on the sensor, plug USB-C, wait for /Volumes/RPI-RP2 ...")
    try:
        flash()
    except KeyboardInterrupt:
        print("\nstopped")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
