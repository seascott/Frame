from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

RP2040_VID = "2e8a"  # Raspberry Pi Pico / RP2040
BOOTSEL_VOLUME = Path("/Volumes/RPI-RP2")
BOOTSEL_PIDS = {"0003"}  # RP2 Boot
CDC_PIDS = {"000a", "0009", "0005"}


@dataclass(frozen=True)
class UsbDevice:
    name: str
    vendor_id: str
    product_id: str
    location: str


def bootsel_mounted() -> bool:
    return BOOTSEL_VOLUME.exists()


def usb_devices() -> list[UsbDevice]:
    raw = subprocess.check_output(
        ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
        text=True,
    )
    devices: list[UsbDevice] = []
    name = ""
    vendor = ""
    product = ""
    location = ""

    def flush() -> None:
        nonlocal name, vendor, product, location
        if name and vendor:
            devices.append(UsbDevice(name, vendor, product, location))
        name = vendor = product = location = ""

    skip_names = {"USB", "Media", "STORAGE DEVICE"}
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("Host Controller Driver:"):
            continue
        if stripped.endswith(":") and ":" not in stripped[:-1]:
            key = stripped[:-1]
            if key in skip_names or key.endswith(" Bus"):
                continue
            flush()
            name = key
            continue
        if stripped.startswith("Product ID:"):
            product = stripped.split(":", 1)[1].strip().replace("0x", "").lower()
        elif stripped.startswith("Vendor ID:"):
            vendor = stripped.split(":", 1)[1].strip().split()[0].replace("0x", "").lower()
        elif stripped.startswith("Location ID:"):
            location = stripped.split(":", 1)[1].strip()
    flush()
    return devices


def rp2040_devices(devices: list[UsbDevice] | None = None) -> list[UsbDevice]:
    devices = devices if devices is not None else usb_devices()
    return [d for d in devices if d.vendor_id == RP2040_VID]


def discovery_state() -> str:
    """invisible | bootsel | cdc | unknown-rp2040"""
    if bootsel_mounted():
        return "bootsel"
    found = rp2040_devices()
    if not found:
        return "invisible"
    if any(d.product_id in BOOTSEL_PIDS for d in found):
        return "bootsel"
    if any(d.product_id in CDC_PIDS for d in found):
        return "cdc"
    return "unknown-rp2040"


def report() -> str:
    devices = usb_devices()
    lines = [
        f"Discovery state: {discovery_state()}",
        f"BOOTSEL volume: {'yes ' + str(BOOTSEL_VOLUME) if bootsel_mounted() else 'no'}",
        "",
        "USB devices:",
    ]
    if not devices:
        lines.append("  (none)")
    for device in devices:
        mark = ""
        if device.vendor_id == RP2040_VID:
            mark = "  <- RP2040"
        lines.append(
            f"  {device.name}  vid={device.vendor_id} pid={device.product_id}  {device.location}{mark}"
        )
    rp = rp2040_devices(devices)
    if not rp and not bootsel_mounted():
        lines += [
            "",
            "The SEN0628 is not enumerating. Stock firmware already speaks USB CDC;",
            "there is no extra discovery image. If the board is blank or stuck,",
            "hold BOOT while plugging USB-C until /Volumes/RPI-RP2 appears, then:",
            "  python -m frame.flash",
        ]
    return "\n".join(lines)


def main() -> int:
    print(report())
    state = discovery_state()
    return 0 if state in {"cdc", "bootsel"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
