from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from frame.constants import SLIDE_SECONDS
from frame.gestures import Gesture
from frame.schema import MOTION_IMAGE, MOTION_NONE, MOTION_VIDEO


@dataclass(frozen=True)
class Slide:
    still: Path
    motion: Path | None
    title: str
    orientation: str
    kind: str = "photo"
    token: str = ""

    @property
    def playable(self) -> bool:
        return self.motion is not None

    @property
    def motion_type(self) -> str:
        if self.motion is None:
            return MOTION_NONE
        if self.motion.suffix.lower() in {".gif", ".webp"}:
            return MOTION_IMAGE
        return MOTION_VIDEO


class Slideshow:
    def __init__(self, slides: list[Slide], dwell_seconds: float = SLIDE_SECONDS) -> None:
        if not slides:
            raise ValueError("slideshow needs at least one image")
        self.slides = slides
        self.dwell_seconds = dwell_seconds
        self._index = 0
        self.playing = False
        self.armed = False
        self.generation = 0
        self.last_command = "none"
        self.cue = ""
        self.cue_id = 0
        self.sensor = "disconnected"
        self.source = ""
        self._deadline = time.monotonic() + dwell_seconds
        self._lock = threading.Lock()
        self._by_token = {slide.token: slide for slide in slides if slide.token}

    @property
    def current(self) -> Slide:
        return self.slides[self._index]

    def slide_by_token(self, token: str) -> Slide | None:
        return self._by_token.get(token)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            slide = self.slides[self._index]
            remaining = max(0.0, self._deadline - time.monotonic())
            motion_type = slide.motion_type
            token = slide.token or str(self._index)
            return {
                "index": self._index,
                "total": len(self.slides),
                "still_src": f"/media/{token}/still",
                "motion_src": f"/media/{token}/motion" if slide.playable else "",
                "motion_type": motion_type,
                "title": slide.title,
                "orientation": slide.orientation,
                "kind": slide.kind,
                "playable": slide.playable,
                "playing": self.playing,
                "armed": self.armed,
                "generation": self.generation,
                "last_command": self.last_command,
                "cue": self.cue,
                "cue_id": self.cue_id,
                "sensor": self.sensor,
                "source": self.source,
                "remaining": round(remaining, 2),
            }

    def tick(self) -> None:
        with self._lock:
            if self.playing:
                return
            if time.monotonic() >= self._deadline:
                self._move(1, "auto")

    def apply_gesture(self, gesture: Gesture) -> None:
        if gesture is Gesture.SWIPE_LEFT:
            self.next("swipe_left")
        elif gesture is Gesture.SWIPE_RIGHT:
            self.previous("swipe_right")
        elif gesture is Gesture.PLAY:
            self.play("push")
        elif gesture is Gesture.STOP:
            self.stop("withdraw")

    def next(self, source: str = "next") -> None:
        with self._lock:
            self._move(1, source)
            self._flash("swipe_left")

    def previous(self, source: str = "previous") -> None:
        with self._lock:
            self._move(-1, source)
            self._flash("swipe_right")

    def play(self, source: str = "play") -> None:
        with self._lock:
            if self.playing:
                self._stop(source)
                return
            if not self.slides[self._index].playable:
                return
            self.playing = True
            self.last_command = source
            self._flash("play")

    def stop(self, source: str = "stop") -> None:
        with self._lock:
            self._stop(source)

    def set_sensor(self, status: str) -> None:
        with self._lock:
            self.sensor = status

    def set_armed(self, armed: bool) -> None:
        with self._lock:
            self.armed = armed

    def set_source(self, source: str) -> None:
        with self._lock:
            self.source = source

    def _stop(self, source: str) -> None:
        if not self.playing:
            return
        self.playing = False
        self.last_command = source
        self.generation += 1
        self._deadline = time.monotonic() + self.dwell_seconds
        self._flash("pause")

    def _move(self, delta: int, source: str) -> None:
        self._index = (self._index + delta) % len(self.slides)
        self.generation += 1
        self.playing = False
        self.last_command = source
        self._deadline = time.monotonic() + self.dwell_seconds

    def _flash(self, cue: str) -> None:
        self.cue = cue
        self.cue_id += 1
