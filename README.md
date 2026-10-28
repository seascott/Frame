# frame

Gesture-controlled digital photo frame: scan a folder of photos and videos, render a Ken Burns slideshow in a browser preview (and eventually on an LED matrix), and drive playback with hand gestures from a DFRobot **SEN0628** 8×8 time-of-flight sensor over USB serial.

The Python package lives under `frame/`. Mac development uses the sensor’s USB-C CDC port; the same serial path is intended to work on a Raspberry Pi runtime later.

## Stack

- **Python 3** — package under `frame/`
- **Pillow** — still derive, EXIF orientation, cache
- **pyserial** — SEN0628 USB CDC stream
- **ffmpeg** (optional, on `PATH`) — video transcode and some demo assets
- **Static web UI** — `frame/web/` served by `preview.py`

Agent conventions and the tiered review ladder: **`CLAUDE.md`**.

## Hardware and firmware

- **Sensor:** DFRobot SEN0628 (8×8 ToF grid, RP2040 USB).
- **Connection:** Plug the sensor’s **USB-C data** port into the host (not the 4-pin Gravity I2C lead). At 115200 baud it streams ASCII rows such as `Y0: …` with per-cell distances in millimetres.
- **Firmware:** Stock DFRobot UF2 is bundled at `firmware/SEN0628-V1.3-20250904.uf2`.

If the board is blank or stuck in BOOTSEL, hold **BOOT** while plugging USB-C until the `RPI-RP2` volume appears, then flash:

```bash
python -m frame.flash
```

USB discovery and troubleshooting:

```bash
python -m frame.discover
```

## Install

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dependencies: **Pillow** (image derive/cache) and **pyserial** (sensor).

Optional: **ffmpeg** on `PATH` for video transcoding and some demo assets (`derive.py` invokes it when needed).

## Module map (`frame/`)

| Module | Role |
|--------|------|
| `player.py` | `Slideshow` and `Slide` models; dwell timer, Ken Burns vs motion playback, gesture command handling. |
| `library.py` | Walk a media folder; pair Live Photo stills with sidecar video; classify photos, GIFs, and videos. |
| `derive.py` | Build web-displayable stills and motion files into a cache (EXIF orientation, embedded motion, ffmpeg). |
| `gestures.py` | `GestureClassifier` on 8×8 depth frames: swipe left/right, push to play, withdraw to stop. |
| `sensor.py` | `UsbMatrixSensor` serial reader; port auto-detection and probe helpers. |
| `matrix.py` | Parse USB ASCII into `DepthFrame`; frame buffering (`pop_usb_frames`). |
| `storage.py` | `FRAME_LIBRARY` / removable volume discovery; per-library cache directory helpers. |
| `discover.py` | macOS USB inventory and RP2040 BOOTSEL vs CDC state; human-readable `report()`. |
| `flash.py` | Copy the bundled UF2 onto `RPI-RP2` for firmware recovery. |
| `selftest.py` | Offline tests for matrix parsing, gesture logic, library pairing, and derive edge cases. |
| `preview.py` | Local HTTP server plus `frame/web/` UI: full library preview with optional live sensor control. |
| `breadboard.py` | Terminal heatmap and gesture breadboard on Mac USB (default `python -m frame` entry). |
| `constants.py` | Shared sensor, grid, and gesture tuning. |
| `schema.py` | File suffixes, skip rules, and cache directory names. |

Supporting modules: `demo_library.py` (generated mixed demo under `assets/demo/`), `test_images.py`, `test_library.py` (validation corpus under `assets/validation/`).

## Gestures

With background learning and a short presence arm time, in the control volume (~20–75 cm):

- **Swipe left / right** — next / previous slide  
- **Push toward the sensor** — play motion (GIF/video/Live Photo)  
- **Pull away** — pause / return to Ken Burns on the still  

## Test

No hardware required. This is the default **prove** command for merges and regressions:

```bash
python3 -m frame.selftest
```

Prints `ok` when all checks pass (matrix parsing, gestures, library pairing, derive edge cases).

## Run the preview

Starts a browser slideshow on `http://127.0.0.1:8765/` by default. Connects to the first detected SEN0628 serial port unless `--no-sensor` is set.

```bash
# Demo library (or first removable volume if set; otherwise demo fallback)
python -m frame.preview --demo

# Explicit folder (SD card, USB stick, or local directory)
python -m frame.preview --library /path/to/photos

# First removable volume
python -m frame.preview --discover

# Original labeled test GIFs
python -m frame.preview --test-media

# Full validation library (builds assets/validation/ if needed)
python -m frame.preview --test-library

# Preview only, no gesture sensor
python -m frame.preview --demo --no-sensor
```

Environment variable **`FRAME_LIBRARY`** can point at a default library directory (see `storage.resolve_library_root`).

## Live sensor breadboard

Terminal UI for tuning gestures without the web preview:

```bash
python -m frame              # same as python -m frame.breadboard
python -m frame --probe      # list USB/serial candidates
python -m frame --wait       # block until a serial port appears
python -m frame --raw        # dump the USB stream
```

## Scan a library (CLI)

```bash
python -m frame.library /path/to/photos
```

Lists paired assets without starting the preview server.
