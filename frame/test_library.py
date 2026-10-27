"""Generate a comprehensive, labeled validation library.

Every item exercises a different capability of the frame pipeline so a human can
eyeball one slideshow and confirm the whole feature set works:

  * stills at every aspect ratio (landscape / portrait / square / panorama)
  * alternate still encodings (PNG with alpha, WebP)
  * an animated GIF (image motion)
  * standalone videos in both MP4 and MOV containers
  * a Live Photo pair (still + short motion clip sharing one stem)
  * an EXIF-rotated still (orientation handling)
  * a tiny still (upscale path)

Each asset is burned with an on-image label describing what it validates, so the
operator reads the frame and knows exactly which capability is on screen.

Run standalone to (re)build and print the scan summary:
    python -m frame.test_library
Or serve it:
    python -m frame.preview --test-library --no-sensor
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from frame.test_images import _font, _gradient  # shared rendering helpers

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_LIBRARY_DIR = REPO_ROOT / "assets" / "validation"
MEDIA_VERSION = "validation-v1"

RGB = tuple[int, int, int]

# Motion clips: short and low-fps so generation stays quick on weak hardware.
MOTION_FRAMES = 24
MOTION_FPS = 12


@dataclass(frozen=True)
class LibItem:
    """One capability under test. `formats` drives which files are emitted."""

    stem: str
    title: str
    note: str                 # the capability this validates, shown on-screen
    size: tuple[int, int]
    top: RGB
    bottom: RGB
    formats: tuple[str, ...]  # subset of: jpg png webp gif mp4 mov live exif tiny


ITEMS: tuple[LibItem, ...] = (
    LibItem("01_landscape", "Landscape", "16:9 still - Ken Burns pan/zoom",
            (1920, 1080), (12, 40, 78), (52, 150, 170), ("jpg",)),
    LibItem("02_portrait", "Portrait", "9:16 still - letterboxed, no crop",
            (1080, 1920), (44, 26, 16), (196, 132, 70), ("jpg",)),
    LibItem("03_square", "Square", "1:1 still - cover fit",
            (1080, 1080), (18, 54, 30), (110, 190, 96), ("jpg",)),
    LibItem("04_panorama", "Panorama", "ultra-wide still - edges cropped",
            (2560, 720), (70, 24, 16), (210, 120, 70), ("jpg",)),
    LibItem("05_png_alpha", "PNG Alpha", "PNG transparency over black",
            (1200, 1200), (24, 28, 44), (90, 120, 200), ("png",)),
    LibItem("06_webp", "WebP", "WebP still decode",
            (1600, 900), (40, 20, 52), (170, 96, 210), ("webp",)),
    LibItem("07_animated", "Animated GIF", "GIF motion - plays on push",
            (960, 540), (10, 44, 60), (60, 170, 180), ("gif",)),
    LibItem("08_video_mp4", "Video MP4", "H.264/MP4 - plays on push",
            (1280, 720), (54, 18, 18), (200, 90, 70), ("mp4",)),
    LibItem("09_video_mov", "Video MOV", "H.264/MOV container - plays on push",
            (1280, 720), (18, 34, 54), (90, 140, 200), ("mov",)),
    LibItem("10_live_photo", "Live Photo", "still + .mov pair - push to play",
            (1440, 1080), (30, 40, 24), (150, 190, 110), ("live",)),
    LibItem("11_exif_rotated", "EXIF Rotated", "EXIF orientation=6 (90 CW)",
            (1920, 1080), (52, 38, 12), (210, 170, 70), ("exif",)),
    LibItem("12_tiny", "Tiny", "200x150 source - upscaled",
            (800, 600), (28, 28, 34), (120, 120, 150), ("tiny",)),
)


def ensure_test_library(directory: Path = TEST_LIBRARY_DIR) -> Path:
    """Build (or refresh) the validation library and return its folder."""
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".media-version"
    if not marker.exists() or marker.read_text().strip() != MEDIA_VERSION:
        for old in directory.glob("*"):
            if old.name != ".media-version":
                old.unlink()
    for index, item in enumerate(ITEMS, start=1):
        _build_item(directory, index, item)
    marker.write_text(MEDIA_VERSION + "\n")
    return directory


def _build_item(directory: Path, number: int, item: LibItem) -> None:
    for fmt in item.formats:
        if fmt in {"jpg", "png", "webp", "tiny", "exif"}:
            _build_still(directory, number, item, fmt)
        elif fmt == "gif":
            _build_gif(directory, number, item)
        elif fmt in {"mp4", "mov"}:
            _build_video(directory, number, item, fmt)
        elif fmt == "live":
            _build_live(directory, number, item)


def _label_lines(number: int, item: LibItem, size: tuple[int, int], tag: str) -> list[str]:
    return [f"{number:02d}  {item.title}", item.note, f"{size[0]}x{size[1]} - {tag}"]


def _compose(item: LibItem, size: tuple[int, int], lines: list[str], motion_phase: float | None = None) -> Image.Image:
    """Gradient background + optional moving marker + burned-in labels."""
    image = _gradient(size[0], size[1], item.top, item.bottom).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = size
    if motion_phase is not None:
        # a bright marker that sweeps left->right so motion is unmistakable
        cx = int(width * (0.1 + 0.8 * motion_phase))
        cy = int(height * 0.42)
        r = max(16, int(min(width, height) * 0.07))
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 220))
    _draw_labels(draw, number_lines=lines, width=width, height=height)
    return image


def _draw_labels(draw: ImageDraw.ImageDraw, number_lines: list[str], width: int, height: int) -> None:
    pad = int(min(width, height) * 0.05)
    big = _font(max(22, int(height * 0.085)))
    small = _font(max(14, int(height * 0.045)))
    # translucent plate for legibility over any gradient
    plate_h = int(height * 0.30)
    draw.rectangle((0, height - plate_h, width, height), fill=(0, 0, 0, 120))
    y = height - plate_h + pad // 2
    for i, line in enumerate(number_lines):
        font = big if i == 0 else small
        draw.text((pad, y), line, font=font, fill=(255, 255, 255, 235))
        y += int(font.size * 1.25) if hasattr(font, "size") else int(height * 0.08)


def _build_still(directory: Path, number: int, item: LibItem, fmt: str) -> None:
    if fmt == "tiny":
        size, ext, tag = (200, 150), "jpg", "tiny source"
    elif fmt == "exif":
        size, ext, tag = item.size, "jpg", "exif o=6"
    else:
        size, ext, tag = item.size, fmt, fmt
    dest = directory / f"{item.stem}.{ext}"
    if dest.exists() and dest.stat().st_size > 0:
        return
    image = _compose(item, size, _label_lines(number, item, size, tag))
    if fmt == "png":
        rgba = image.convert("RGBA")
        _punch_alpha(rgba)  # transparent corners to prove alpha handling
        rgba.save(dest)
    elif fmt == "webp":
        image.save(dest, "WEBP", quality=90)
    elif fmt == "exif":
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: rotate 90 CW on display
        image.save(dest, "JPEG", quality=90, exif=exif)
    else:
        image.save(dest, "JPEG", quality=90)


def _punch_alpha(image: Image.Image) -> None:
    width, height = image.size
    pixels = image.load()
    cut = int(min(width, height) * 0.16)
    for y in range(height):
        for x in range(width):
            if (x < cut and y < cut) or (x > width - cut and y < cut):
                pixels[x, y] = (0, 0, 0, 0)


def _build_gif(directory: Path, number: int, item: LibItem) -> None:
    dest = directory / f"{item.stem}.gif"
    if dest.exists() and dest.stat().st_size > 0:
        return
    frames = [
        _compose(item, item.size, _label_lines(number, item, item.size, "gif"), motion_phase=i / (MOTION_FRAMES - 1))
        .convert("P", palette=Image.ADAPTIVE, colors=128)
        for i in range(MOTION_FRAMES)
    ]
    frames[0].save(dest, save_all=True, append_images=frames[1:], duration=1000 // MOTION_FPS, loop=0, disposal=2)


def _build_video(directory: Path, number: int, item: LibItem, container: str) -> None:
    dest = directory / f"{item.stem}.{container}"
    if dest.exists() and dest.stat().st_size > 1000:
        return
    _encode_video(item, number, dest, f"{container} video")


def _build_live(directory: Path, number: int, item: LibItem) -> None:
    still = directory / f"{item.stem}.jpg"
    motion = directory / f"{item.stem}.mov"  # same stem -> paired as Live Photo
    if not (still.exists() and still.stat().st_size > 0):
        image = _compose(item, item.size, _label_lines(number, item, item.size, "live still"))
        image.save(still, "JPEG", quality=90)
    if not (motion.exists() and motion.stat().st_size > 1000):
        _encode_video(item, number, motion, "live motion")


def _encode_video(item: LibItem, number: int, dest: Path, tag: str) -> None:
    """Render labeled moving frames with Pillow, encode to H.264 via ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        dest.write_bytes(b"")  # placeholder; scan still records the item
        return
    size = item.size
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for i in range(MOTION_FRAMES):
            frame = _compose(item, size, _label_lines(number, item, size, tag), motion_phase=i / (MOTION_FRAMES - 1))
            frame.save(tmp_dir / f"f_{i:03d}.png")
        subprocess.run(
            [
                ffmpeg, "-y", "-framerate", str(MOTION_FPS),
                "-i", str(tmp_dir / "f_%03d.png"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(dest),
            ],
            check=False,
            capture_output=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the frame validation library")
    parser.add_argument("--dir", type=Path, default=TEST_LIBRARY_DIR)
    args = parser.parse_args(argv)
    root = ensure_test_library(args.dir)

    from frame.library import scan_library, summarize

    assets = scan_library(root)
    print(f"Validation library: {root}")
    print(summarize(assets))
    for asset in assets:
        motion = (
            asset.motion_source.name
            if asset.motion_source
            else ("embedded" if asset.embedded_motion else "-")
        )
        still = asset.still_source.name if asset.still_source else "-"
        print(f"  {asset.kind:6}  {asset.title:16}  still={still:22}  motion={motion}")
    return 0 if assets else 1


if __name__ == "__main__":
    raise SystemExit(main())
