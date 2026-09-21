from __future__ import annotations

import argparse
import sys
import time

from frame.constants import GRID_SIZE, INVALID_DISTANCE_MM
from frame.gestures import Gesture, GestureClassifier, hand_centroid
from frame.matrix import DepthFrame, is_hand_range, is_valid_range
from frame.discover import report as usb_report
from frame.sensor import (
    UsbMatrixSensor,
    candidate_serial_ports,
    describe_serial_ports,
    wait_for_port,
)

BLOCKS = " ░▒▓█"
HELP = """SEN0628 Mac breadboard

Plug the sensor USB-C port into this Mac with a data cable
(not the 4-pin Gravity I2C lead). It should appear as /dev/cu.usbmodem*.

Then put a hand in the control volume (~20-75 cm), wait a beat:
  swipe left / right  -> next / previous
  push toward sensor  -> play GIF
"""


def render_heatmap(frame: DepthFrame, centroid: tuple[float, float, float] | None) -> str:
    lines: list[str] = []
    cx = round(centroid[0]) if centroid else -1
    cy = round(centroid[1]) if centroid else -1
    for y in range(GRID_SIZE):
        cells: list[str] = []
        for x in range(GRID_SIZE):
            mm = frame.at(x, y)
            glyph = _glyph(mm)
            if x == cx and y == cy:
                glyph = "*"
            cells.append(glyph)
        row_mm = " ".join(f"{frame.at(x, y):4d}" for x in range(GRID_SIZE))
        lines.append("".join(cells) + "   " + row_mm)
    return "\n".join(lines)


def _glyph(mm: int) -> str:
    if not is_valid_range(mm) or mm >= INVALID_DISTANCE_MM:
        return "."
    if not is_hand_range(mm):
        return "·"
    # Nearer hands are denser.
    t = (900 - mm) / 750
    index = max(1, min(len(BLOCKS) - 1, int(t * (len(BLOCKS) - 1))))
    return BLOCKS[index]


def run_live(port: str, raw: bool) -> int:
    classifier = GestureClassifier()
    last_event = "none"
    frames = 0
    started = time.monotonic()
    print(f"Opening {port} at 115200")
    with UsbMatrixSensor(port) as sensor:
        if raw:
            return _dump_raw(sensor)
        for frame in sensor.frames():
            now = time.monotonic()
            frames += 1
            event = classifier.update(now, frame)
            centroid = classifier.last_centroid
            if event is not None:
                last_event = event.gesture.value
                command = {
                    Gesture.SWIPE_LEFT: "NEXT",
                    Gesture.SWIPE_RIGHT: "PREVIOUS",
                    Gesture.PLAY: "PLAY GIF",
                    Gesture.STOP: "PAUSE / KEN BURNS",
                }[event.gesture]
                print(f"\n>>> {event.gesture.value:12} -> {command}")
            hz = frames / max(0.001, now - started)
            z = f"{centroid[2]:.0f} mm" if centroid else "no hand"
            sys.stdout.write("\033[H\033[J")
            print("SEN0628 breadboard   q to quit in the terminal with Ctrl-C")
            print(f"port {port}   {hz:4.1f} Hz   hand {z}   armed {classifier.armed}   last {last_event}")
            print()
            print(render_heatmap(frame, centroid))
            print()
            print("arm in the control volume, then swipe or push-to-play")
            sys.stdout.flush()
    return 0


def _dump_raw(sensor: UsbMatrixSensor) -> int:
    print("Raw serial dump. Ctrl-C to stop.")
    while True:
        chunk = sensor.read_chunk()
        if chunk:
            sys.stdout.write(chunk)
            sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Breadboard SEN0628 gestures on Mac USB")
    parser.add_argument("--port", help="Serial device, default auto-detect")
    parser.add_argument("--wait", action="store_true", help="Wait until a USB serial device appears")
    parser.add_argument("--raw", action="store_true", help="Print the USB stream without parsing")
    parser.add_argument("--probe", action="store_true", help="List serial devices and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.probe:
        print(HELP)
        print(usb_report())
        print()
        print("Serial ports:")
        print(describe_serial_ports())
        print("Candidates:", candidate_serial_ports() or "(none)")
        return 0
    port = args.port
    if port is None:
        ports = candidate_serial_ports()
        if not ports:
            print(HELP)
            print("No SEN0628 USB serial device yet.")
            print("Serial ports:")
            print(describe_serial_ports())
            if not args.wait:
                print("\nRe-run with --wait after plugging the USB-C data cable into the sensor.")
                return 2
            print("Waiting for /dev/cu.usbmodem* ...")
            port = wait_for_port()
        else:
            port = ports[0]
    try:
        return run_live(port, raw=args.raw)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
