"""Build a small mixed photo / live / video / GIF library for local preview."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from frame.library import scan_library
from frame.test_images import TEST_IMAGE_DIR, ensure_test_images

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_LIBRARY_DIR = REPO_ROOT / "assets" / "demo"


def ensure_demo_library(directory: Path = DEMO_LIBRARY_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    media = ensure_test_images()
    harbor_still, harbor_gif, harbor = media[0]
    forest_still, _forest_gif, forest = media[1]
    window_still, window_gif, window = media[6]

    _copy(forest_still, directory / "Forest.jpg")
    _copy(window_still, directory / "Window.jpg")
    _copy(harbor_gif, directory / "Harbor.gif")

    live_still = directory / "Live Harbor.jpg"
    live_motion = directory / "Live Harbor.MOV"
    _copy(harbor_still, live_still)
    _render_clip(live_still, live_motion, seconds=1.6)

    clip = directory / "Waves.mp4"
    _render_clip(forest_still, clip, seconds=2.4)

    _copy(window_gif, directory / "Window Loop.gif")
    return directory


def ensure_demo_assets() -> tuple[Path, list]:
    root = ensure_demo_library()
    return root, scan_library(root)


def _copy(source: Path, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    shutil.copy2(source, dest)


def _render_clip(still: Path, dest: Path, seconds: float) -> None:
    if dest.exists() and dest.stat().st_size > 1000:
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        dest.write_bytes(b"")
        return
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(still),
            "-t",
            f"{seconds:.2f}",
            "-vf",
            "scale=960:540,format=yuv420p",
            "-an",
            str(dest),
        ],
        check=False,
        capture_output=True,
    )
