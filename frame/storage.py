"""Find removable library roots (SD cards, USB drives) and a writable cache."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from frame.schema import CACHE_DIR_NAME, SKIP_VOLUME_NAMES


def discover_volumes() -> list[Path]:
    """Mounted volumes that are not the boot disk."""
    found: list[Path] = []
    boot = Path("/").resolve()
    try:
        boot_dev = boot.stat().st_dev
    except OSError:
        boot_dev = None
    for candidate in _volume_candidates():
        if not candidate.is_dir():
            continue
        if candidate.name.startswith("."):
            continue
        if candidate.name.lower() in SKIP_VOLUME_NAMES:
            continue
        if not os.access(candidate, os.R_OK):
            continue
        try:
            if boot_dev is not None and candidate.resolve().stat().st_dev == boot_dev:
                continue
        except OSError:
            continue
        found.append(candidate)
    return sorted(found, key=lambda path: path.name.lower())


def resolve_library_root(explicit: str | Path | None = None) -> Path | None:
    """Prefer an explicit folder, then FRAME_LIBRARY, then the first removable volume."""
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        return path if path.is_dir() else None
    env = os.environ.get("FRAME_LIBRARY")
    if env:
        path = Path(env).expanduser().resolve()
        if path.is_dir():
            return path
    volumes = discover_volumes()
    return volumes[0] if volumes else None


def cache_dir_for(library: Path, fallback: Path | None = None) -> Path:
    """Write derived stills beside the library when possible, else locally."""
    sibling = library / CACHE_DIR_NAME
    if _can_write(sibling):
        return sibling
    if fallback is not None:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    home = Path.home() / ".frame" / "cache"
    home.mkdir(parents=True, exist_ok=True)
    return home


def _volume_candidates() -> list[Path]:
    paths: list[Path] = []
    if sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            paths.extend(volumes.iterdir())
        return paths
    user = os.environ.get("USER", "")
    for root in (
        Path("/media") / user,
        Path("/run/media") / user,
        Path("/media"),
        Path("/mnt"),
        Path("/run/media"),
    ):
        if root.is_dir():
            paths.extend(path for path in root.iterdir() if path.is_dir())
    return paths


def _can_write(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
