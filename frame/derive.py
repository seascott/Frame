"""Turn library assets into web-displayable stills and motion files."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from frame.library import MediaAsset
from frame.player import Slide
from frame.schema import KIND_GIF, STILL_WEB_SUFFIXES

LOGGER = logging.getLogger(__name__)


def asset_token(asset: MediaAsset) -> str:
    raw = "|".join(
        str(path.resolve()) if path is not None else ""
        for path in (asset.still_source, asset.motion_source)
    )
    raw += f"|{asset.kind}|{int(asset.embedded_motion)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_slides(assets: list[MediaAsset], cache_dir: Path) -> list[Slide]:
    slides: list[Slide] = []
    for asset in assets:
        slide = prepare_slide(asset, cache_dir)
        if slide is not None:
            slides.append(slide)
    return slides


def prepare_slide(asset: MediaAsset, cache_dir: Path) -> Slide | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = asset_token(asset)
    still = _ensure_still(asset, cache_dir, token)
    if still is None:
        LOGGER.warning("skip %s: no display still", asset.title)
        return None
    motion = _ensure_motion(asset, cache_dir, token)
    orientation = _orientation(still)
    return Slide(
        still=still,
        motion=motion,
        title=asset.title,
        orientation=orientation,
        kind=asset.kind,
        token=token,
    )


def motion_type_for(slide: Slide) -> str:
    return slide.motion_type


def extract_embedded_motion(source: Path, dest: Path) -> bool:
    """Copy the trailing MP4 out of a Motion Photo JPEG/HEIC."""
    try:
        data = source.read_bytes()
    except OSError:
        return False
    offset = _microvideo_offset(data)
    if offset is None:
        idx = data.rfind(b"ftyp")
        if idx >= 4 and (b"MicroVideo" in data or b"MotionPhoto" in data):
            offset = len(data) - (idx - 4)
    if offset is None or offset < 16 or offset >= len(data):
        return False
    dest.write_bytes(data[-offset:])
    return dest.stat().st_size >= 16


def _ensure_still(asset: MediaAsset, cache_dir: Path, token: str) -> Path | None:
    source = asset.still_source or asset.motion_source
    if source is None:
        return None
    suffix = source.suffix.lower()
    if asset.kind != KIND_GIF and suffix in STILL_WEB_SUFFIXES:
        return source
    dest = cache_dir / f"{token}-still.jpg"
    if dest.is_file() and dest.stat().st_mtime >= _mtime(source):
        return dest
    if suffix in {".gif"} or asset.kind == KIND_GIF:
        return _gif_still(source, dest)
    if suffix in {".heic", ".heif"}:
        return _heic_still(source, dest)
    if suffix in {".mp4", ".m4v", ".mov", ".webm"}:
        return _video_poster(source, dest) or _placeholder_still(dest, asset.title)
    try:
        with Image.open(source) as image:
            image.convert("RGB").save(dest, quality=90)
        return dest
    except OSError:
        return _placeholder_still(dest, asset.title)


def _ensure_motion(asset: MediaAsset, cache_dir: Path, token: str) -> Path | None:
    if asset.motion_source is not None:
        return asset.motion_source
    if not asset.embedded_motion or asset.still_source is None:
        return None
    dest = cache_dir / f"{token}-motion.mp4"
    if dest.is_file() and dest.stat().st_mtime >= _mtime(asset.still_source):
        return dest
    if extract_embedded_motion(asset.still_source, dest):
        return dest
    return None


def _gif_still(source: Path, dest: Path) -> Path | None:
    try:
        with Image.open(source) as image:
            image.seek(0)
            image.convert("RGB").save(dest, quality=90)
        return dest
    except OSError:
        return None


def _heic_still(source: Path, dest: Path) -> Path | None:
    sips = shutil.which("sips")
    if sips:
        result = subprocess.run(
            [sips, "-s", "format", "jpeg", "-s", "formatOptions", "80", str(source), "--out", str(dest)],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0 and dest.is_file():
            return dest
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        with Image.open(source) as image:
            image.convert("RGB").save(dest, quality=90)
        return dest
    except (ImportError, OSError):
        return None


def _video_poster(source: Path, dest: Path) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(source), "-frames:v", "1", "-q:v", "3", str(dest)],
        check=False,
        capture_output=True,
    )
    if result.returncode == 0 and dest.is_file():
        return dest
    return None


def _placeholder_still(dest: Path, title: str) -> Path:
    image = Image.new("RGB", (1280, 720), (18, 18, 22))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.text((48, 320), title or "Video", fill=(230, 230, 230))
    image.save(dest, quality=88)
    return dest


def _orientation(path: Path) -> str:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except OSError:
        return "landscape"
    return "portrait" if height > width else "landscape"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _microvideo_offset(data: bytes) -> int | None:
    match = re.search(br"MicroVideoOffset[^0-9]{0,16}(\d+)", data)
    if not match:
        return None
    return int(match.group(1))
