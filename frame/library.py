"""Scan a mixed photo/video folder and pair Live Photos with their motion clips."""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from frame.schema import (
    GIF_SUFFIXES,
    KIND_GIF,
    KIND_LIVE,
    KIND_PHOTO,
    KIND_VIDEO,
    LIVE_VIDEO_MAX_BYTES,
    PHOTO_SUFFIXES,
    SKIP_DIR_NAMES,
    VIDEO_SUFFIXES,
)


@dataclass(frozen=True)
class MediaAsset:
    kind: str
    title: str
    still_source: Path | None
    motion_source: Path | None
    embedded_motion: bool = False
    mtime: float = 0.0

    @property
    def playable(self) -> bool:
        return self.motion_source is not None or self.embedded_motion


def scan_library(root: Path) -> list[MediaAsset]:
    """Walk `root` and return playlist assets, pairing Live Photo sidecars."""
    files = list(_iter_media_files(root))
    return pair_assets(files)


def pair_assets(files: list[Path]) -> list[MediaAsset]:
    """Turn loose files into photos, GIFs, videos, and Live Photo pairs."""
    buckets: dict[str, dict[str, Path]] = defaultdict(dict)
    leftovers: list[Path] = []
    for path in files:
        suffix = path.suffix.lower()
        if suffix in PHOTO_SUFFIXES or suffix in GIF_SUFFIXES or suffix in VIDEO_SUFFIXES:
            buckets[_pair_key(path)][suffix] = path
        else:
            leftovers.append(path)

    assets: list[MediaAsset] = []
    used: set[Path] = set()
    for _key, group in buckets.items():
        photo = _first(group, PHOTO_SUFFIXES)
        gif = _first(group, GIF_SUFFIXES)
        video = _first(group, VIDEO_SUFFIXES)
        if photo is not None and video is not None and _looks_like_live_pair(photo, video):
            assets.append(_asset(KIND_LIVE, photo, photo, video))
            used.add(photo)
            used.add(video)
            continue
        if gif is not None:
            assets.append(_asset(KIND_GIF, gif, gif, gif))
            used.add(gif)
        if photo is not None and photo not in used:
            embedded = has_embedded_motion(photo)
            kind = KIND_LIVE if embedded else KIND_PHOTO
            assets.append(_asset(kind, photo, photo, None, embedded_motion=embedded))
            used.add(photo)
        if video is not None and video not in used:
            assets.append(_asset(KIND_VIDEO, video, None, video))
            used.add(video)

    assets.sort(key=lambda item: (item.title.lower(), item.mtime))
    return assets


def has_embedded_motion(path: Path) -> bool:
    """True when a still JPEG/HEIC looks like a Google/Samsung motion photo."""
    suffix = path.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".heic", ".heif"}:
        return False
    try:
        with path.open("rb") as handle:
            head = handle.read(256 * 1024)
            handle.seek(max(0, path.stat().st_size - 256 * 1024))
            tail = handle.read(256 * 1024)
    except OSError:
        return False
    blob = head + tail
    return any(
        marker in blob
        for marker in (b"MicroVideo", b"MotionPhoto", b"motionphoto", b"GCamera")
    )


def _iter_media_files(root: Path) -> list[Path]:
    found: list[Path] = []
    root = root.expanduser().resolve()
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name.lower() not in SKIP_DIR_NAMES]
        current = Path(dirpath)
        for name in filenames:
            if name.startswith("._") or name.startswith("."):
                continue
            path = current / name
            suffix = path.suffix.lower()
            if suffix in PHOTO_SUFFIXES or suffix in GIF_SUFFIXES or suffix in VIDEO_SUFFIXES:
                found.append(path)
    return found


def _pair_key(path: Path) -> str:
    return f"{path.parent.resolve()}::{path.stem.lower()}"


def _first(group: dict[str, Path], suffixes: frozenset[str]) -> Path | None:
    for suffix in suffixes:
        if suffix in group:
            return group[suffix]
    return None


def _looks_like_live_pair(photo: Path, video: Path) -> bool:
    suffix = video.suffix.lower()
    if suffix == ".mov":
        return True
    if suffix not in {".mp4", ".m4v"}:
        return False
    try:
        return video.stat().st_size <= LIVE_VIDEO_MAX_BYTES
    except OSError:
        return False


def _asset(
    kind: str,
    named: Path,
    still: Path | None,
    motion: Path | None,
    embedded_motion: bool = False,
) -> MediaAsset:
    mtime = 0.0
    for path in (still, motion, named):
        if path is None:
            continue
        try:
            mtime = max(mtime, path.stat().st_mtime)
        except OSError:
            continue
    return MediaAsset(
        kind=kind,
        title=_title(named),
        still_source=still,
        motion_source=motion,
        embedded_motion=embedded_motion,
        mtime=mtime,
    )


def _title(path: Path) -> str:
    stem = path.stem.replace("_", " ").strip()
    return stem or path.name


def summarize(assets: list[MediaAsset]) -> str:
    counts = {KIND_PHOTO: 0, KIND_LIVE: 0, KIND_VIDEO: 0, KIND_GIF: 0}
    for asset in assets:
        counts[asset.kind] = counts.get(asset.kind, 0) + 1
    return (
        f"{len(assets)} items  "
        f"{counts[KIND_PHOTO]} photos  "
        f"{counts[KIND_LIVE]} live  "
        f"{counts[KIND_VIDEO]} videos  "
        f"{counts[KIND_GIF]} gifs"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a frame media library")
    parser.add_argument("root", type=Path, help="SD card, USB volume, or folder")
    args = parser.parse_args(argv)
    assets = scan_library(args.root)
    print(summarize(assets))
    for asset in assets:
        still = asset.still_source.name if asset.still_source else "-"
        motion = asset.motion_source.name if asset.motion_source else ("embedded" if asset.embedded_motion else "-")
        print(f"  {asset.kind:6}  {asset.title:28}  still={still}  motion={motion}")
    return 0 if assets else 1


if __name__ == "__main__":
    raise SystemExit(main())
