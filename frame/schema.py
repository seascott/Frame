"""Library file types, skip rules, and cache names."""

from __future__ import annotations

CACHE_DIR_NAME = ".frame-cache"
INDEX_NAME = "index.json"

PHOTO_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"})
GIF_SUFFIXES = frozenset({".gif"})
VIDEO_SUFFIXES = frozenset({".mp4", ".m4v", ".mov", ".webm"})
STILL_WEB_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})

SKIP_DIR_NAMES = frozenset(
    {
        CACHE_DIR_NAME,
        ".git",
        ".spotlight-v100",
        ".trashes",
        ".fseventsd",
        ".temporaryitems",
        "$recycle.bin",
        "system volume information",
        "@eadir",
        "thumbs",
        ".thumbnails",
        "__macosx",
    }
)

SKIP_VOLUME_NAMES = frozenset(
    {
        "macintosh hd",
        "macintosh hd - data",
        "recovery",
        "com.apple.timemachine.localsnapshots",
    }
)

LIVE_VIDEO_MAX_BYTES = 12 * 1024 * 1024
LIVE_VIDEO_MAX_SECONDS = 4.5

KIND_PHOTO = "photo"
KIND_LIVE = "live"
KIND_VIDEO = "video"
KIND_GIF = "gif"

MOTION_NONE = "none"
MOTION_IMAGE = "image"
MOTION_VIDEO = "video"
