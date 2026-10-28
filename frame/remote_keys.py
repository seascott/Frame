#!/usr/bin/env python3
"""Keyboard remote for the frame.

A kiosk browser on GNOME Wayland does not reliably hold keyboard focus, so an
in-page `keydown` handler misses physical key presses. Instead we read the
keyboard device directly (evdev) and POST the same commands the gesture sensor
drives. Focus-independent, and it turns any USB/BT keyboard into a manual remote
for a sensor-less frame.

Stdlib only. Runs as a small service beside the frame server, as root or as a
user in the `input` group (it needs read access to /dev/input/event*).

    python3 -m frame.remote_keys
"""
from __future__ import annotations

import glob
import json
import re
import struct
import time
import urllib.request

API = "http://127.0.0.1:8765/api/command"

EV_KEY = 0x01
# struct input_event (64-bit): tv_sec, tv_usec (long), type, code (u16), value (i32)
EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

# linux/input-event-codes.h -> frame action. Mirrors the in-page keyboard map.
KEYMAP = {
    106: "next", 108: "next",          # KEY_RIGHT, KEY_DOWN
    105: "previous", 103: "previous",  # KEY_LEFT, KEY_UP
    57: "play", 25: "play",            # KEY_SPACE, KEY_P
    1: "stop",                         # KEY_ESC
    30: "arm_toggle",                  # KEY_A
}


def find_keyboard() -> str | None:
    """Resolve the keyboard event device, preferring stable by-id symlinks."""
    for pattern in ("*K400*event-kbd", "*Keyboard*event-kbd", "*-event-kbd"):
        hits = sorted(glob.glob("/dev/input/by-id/" + pattern))
        if hits:
            return hits[0]
    name = ""
    try:
        with open("/proc/bus/input/devices") as handle:
            for line in handle:
                if line.startswith("N: Name"):
                    name = line
                elif line.startswith("H: Handlers") and "kbd" in line:
                    if any(tag in name for tag in ("K400", "Keyboard", "Logitech")):
                        match = re.search(r"event\d+", line)
                        if match:
                            return "/dev/input/" + match.group(0)
    except OSError:
        pass
    return None


def post(action: str) -> None:
    body = json.dumps({"action": action}).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(request, timeout=3).read()
    except Exception as exc:  # best-effort: a POST blip must never crash the loop
        print(f"frame-keys: POST {action} failed: {exc}", flush=True)


def main() -> int:
    device = find_keyboard()
    while device is None:
        print("frame-keys: no keyboard found yet, retrying...", flush=True)
        time.sleep(2)
        device = find_keyboard()
    print(f"frame-keys: reading {device}", flush=True)
    with open(device, "rb") as handle:
        while True:
            data = handle.read(EVENT_SIZE)
            if len(data) < EVENT_SIZE:
                continue
            _sec, _usec, etype, code, value = struct.unpack(EVENT_FMT, data)
            if etype != EV_KEY or value != 1:  # key-down edge only
                continue
            action = KEYMAP.get(code)
            if action:
                print(f"frame-keys: key {code} -> {action}", flush=True)
                post(action)


if __name__ == "__main__":
    raise SystemExit(main())
