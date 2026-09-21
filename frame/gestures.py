from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum

from frame.constants import (
    BACKGROUND_EMA,
    BACKGROUND_LEARN_FRAMES,
    COMMAND_DEBOUNCE_SECONDS,
    FOREGROUND_DELTA_MM,
    GRID_SIZE,
    HAND_MAX_XY_SPAN,
    HAND_MAX_Z_SPREAD_MM,
    HISTORY_SECONDS,
    INVALID_DISTANCE_MM,
    MAX_HAND_ZONES,
    MIN_HAND_ZONES,
    PRESENCE_ARM_SECONDS,
    PRESENCE_DROP_SECONDS,
    PUSH_MAX_SECONDS,
    PUSH_MAX_XY_CELLS,
    PUSH_MIN_MM,
    PUSH_MIN_SECONDS,
    SWIPE_AGREE,
    SWIPE_MAX_DEPTH_DELTA_MM,
    SWIPE_MAX_SECONDS,
    SWIPE_MIN_CELLS,
    SWIPE_MIN_SAMPLES,
    SWIPE_MIN_SECONDS,
    SWIPE_STEP_EPS,
    ZONE_COUNT,
)
from frame.matrix import DepthFrame, is_hand_range, is_valid_range


class Gesture(str, Enum):
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    PLAY = "play"
    STOP = "stop"


@dataclass(frozen=True)
class HandSample:
    t: float
    x: float
    y: float
    z_mm: float


@dataclass(frozen=True)
class GestureEvent:
    gesture: Gesture
    sample: HandSample | None = None


def hand_centroid(
    frame: DepthFrame,
    background: tuple[float, ...] | None = None,
) -> tuple[float, float, float] | None:
    """Inverse-distance weighted centroid of the largest foreground hand blob."""
    cells = _foreground_cells(frame, background)
    if not cells:
        return None
    blob = max(_connected_blobs(cells), key=len)
    if len(blob) < MIN_HAND_ZONES or len(blob) > MAX_HAND_ZONES:
        return None
    xs = [x for x, _, _ in blob]
    ys = [y for _, y, _ in blob]
    zs = [mm for _, _, mm in blob]
    if max(xs) - min(xs) > HAND_MAX_XY_SPAN or max(ys) - min(ys) > HAND_MAX_XY_SPAN:
        return None
    if max(zs) - min(zs) > HAND_MAX_Z_SPREAD_MM:
        return None
    weight_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    for x, y, mm in blob:
        weight = 1.0 / mm
        x_sum += x * weight
        y_sum += y * weight
        z_sum += mm
        weight_sum += weight
    if weight_sum == 0:
        return None
    return x_sum / weight_sum, y_sum / weight_sum, z_sum / len(blob)


def _foreground_cells(
    frame: DepthFrame,
    background: tuple[float, ...] | None,
) -> dict[tuple[int, int], int]:
    cells: dict[tuple[int, int], int] = {}
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            mm = frame.at(x, y)
            if not is_hand_range(mm):
                continue
            if background is not None:
                baseline = background[y * GRID_SIZE + x]
                if baseline - mm < FOREGROUND_DELTA_MM:
                    continue
            cells[(x, y)] = mm
    return cells


def _connected_blobs(cells: dict[tuple[int, int], int]) -> list[list[tuple[int, int, int]]]:
    seen: set[tuple[int, int]] = set()
    blobs: list[list[tuple[int, int, int]]] = []
    for start in cells:
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        blob: list[tuple[int, int, int]] = []
        while stack:
            x, y = stack.pop()
            blob.append((x, y, cells[(x, y)]))
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                neighbor = (nx, ny)
                if neighbor in cells and neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        blobs.append(blob)
    return blobs


def _background_sample(mm: int) -> float:
    if is_valid_range(mm):
        return float(mm)
    return float(INVALID_DISTANCE_MM)


class GestureClassifier:
    def __init__(self) -> None:
        self._history: deque[HandSample] = deque()
        self._last_command_at = -1e9
        self._present_since: float | None = None
        self._absent_since: float | None = None
        self._background = [float(INVALID_DISTANCE_MM)] * ZONE_COUNT
        self._bg_count = 0
        self.armed = False
        self.last_centroid: tuple[float, float, float] | None = None

    @property
    def background_ready(self) -> bool:
        return self._bg_count >= BACKGROUND_LEARN_FRAMES

    def update(self, t: float, frame: DepthFrame) -> GestureEvent | None:
        self._trim(t)
        if not self.background_ready:
            self._update_background(frame)
            self.last_centroid = None
            return None
        centroid = hand_centroid(frame, tuple(self._background))
        self.last_centroid = centroid
        if centroid is None:
            self._update_background(frame)
            return self._handle_absent(t)
        self._on_present(t)
        sample = HandSample(t=t, x=centroid[0], y=centroid[1], z_mm=centroid[2])
        self._history.append(sample)
        if not self.armed:
            return None
        if t - self._last_command_at < COMMAND_DEBOUNCE_SECONDS:
            return None
        event = self._detect_swipe(sample) or self._detect_push(sample)
        if event is not None:
            self._last_command_at = t
            self._history.clear()
            return event
        return None

    def _handle_absent(self, t: float) -> GestureEvent | None:
        if self.armed and self._history and t - self._last_command_at >= COMMAND_DEBOUNCE_SECONDS:
            event = self._finish_swipe_on_exit(t)
            if event is not None:
                self._last_command_at = t
                self._history.clear()
                self.armed = False
                self._present_since = None
                self._absent_since = t
                return event
        if self._on_absent(t):
            last = self._history[-1] if self._history else HandSample(t=t, x=0, y=0, z_mm=0)
            return GestureEvent(gesture=Gesture.STOP, sample=last)
        return None

    def _finish_swipe_on_exit(self, t: float) -> GestureEvent | None:
        last = self._history[-1]
        recent = list(self._history)[-6:]
        if len(recent) >= 3:
            steps = [recent[index].x - recent[index - 1].x for index in range(1, len(recent))]
            mean_vx = sum(steps) / len(steps)
            span = max(sample.x for sample in recent) - min(sample.x for sample in recent)
            if abs(mean_vx) >= 0.22 and span >= 0.9:
                phantom = HandSample(
                    t=t,
                    x=last.x + (1.8 if mean_vx > 0 else -1.8),
                    y=last.y,
                    z_mm=last.z_mm,
                )
                self._history.append(phantom)
                event = self._detect_swipe(phantom)
                if event is not None:
                    return event
                self._history.pop()
        return self._detect_swipe(last)

    def _on_present(self, t: float) -> None:
        self._absent_since = None
        if self._present_since is None:
            self._present_since = t
        if t - self._present_since >= PRESENCE_ARM_SECONDS:
            if not self.armed:
                self._history.clear()
            self.armed = True

    def _on_absent(self, t: float) -> bool:
        if self._absent_since is None:
            self._absent_since = t
        if t - self._absent_since >= PRESENCE_DROP_SECONDS and self.armed:
            self.armed = False
            self._present_since = None
            self._history.clear()
            return True
        return False

    def _update_background(self, frame: DepthFrame) -> None:
        for index, mm in enumerate(frame.distances_mm):
            sample = _background_sample(mm)
            if self._bg_count == 0:
                self._background[index] = sample
            else:
                previous = self._background[index]
                self._background[index] = previous + BACKGROUND_EMA * (sample - previous)
        self._bg_count += 1

    def _trim(self, t: float) -> None:
        cutoff = t - HISTORY_SECONDS
        while self._history and self._history[0].t < cutoff:
            self._history.popleft()

    def _detect_push(self, current: HandSample) -> GestureEvent | None:
        start = self._oldest_in_window(current.t, PUSH_MAX_SECONDS)
        if start is None:
            return None
        dt = current.t - start.t
        if dt < PUSH_MIN_SECONDS:
            return None
        toward = start.z_mm - current.z_mm
        if toward < PUSH_MIN_MM:
            return None
        if _cell_distance(start, current) > PUSH_MAX_XY_CELLS:
            return None
        recent = [sample for sample in self._history if current.t - sample.t <= PUSH_MAX_SECONDS]
        if len(recent) < 4:
            return None
        mid = len(recent) // 2
        first = sum(sample.z_mm for sample in recent[:mid]) / max(1, mid)
        second = sum(sample.z_mm for sample in recent[mid:]) / max(1, len(recent) - mid)
        if first - second < PUSH_MIN_MM * 0.6:
            return None
        return GestureEvent(gesture=Gesture.PLAY, sample=current)

    def _detect_swipe(self, current: HandSample) -> GestureEvent | None:
        recent = [sample for sample in self._history if current.t - sample.t <= SWIPE_MAX_SECONDS]
        if len(recent) < SWIPE_MIN_SAMPLES:
            return None
        xs = [sample.x for sample in recent]
        min_x = min(xs)
        max_x = max(xs)
        span = max_x - min_x
        if span < SWIPE_MIN_CELLS:
            return None
        right = (_first_index(xs, min_x), _last_index(xs, max_x), Gesture.SWIPE_RIGHT)
        left = (_first_index(xs, max_x), _last_index(xs, min_x), Gesture.SWIPE_LEFT)
        picks = [item for item in (right, left) if item[1] > item[0]]
        if not picks:
            return None
        i0, i1, gesture = max(picks, key=lambda item: item[1])
        if i1 < len(recent) - 3:
            return None
        start = recent[i0]
        end = recent[i1]
        dt = end.t - start.t
        if dt < SWIPE_MIN_SECONDS:
            return None
        if abs(end.y - start.y) > abs(end.x - start.x) + 0.6:
            return None
        if abs(end.z_mm - start.z_mm) > SWIPE_MAX_DEPTH_DELTA_MM:
            return None
        steps = [recent[i + 1].x - recent[i].x for i in range(i0, i1)]
        direction = 1 if gesture is Gesture.SWIPE_RIGHT else -1
        meaningful = [step for step in steps if abs(step) >= SWIPE_STEP_EPS]
        if not meaningful:
            return None
        agreed = sum(1 for step in meaningful if step * direction > 0)
        if agreed < SWIPE_AGREE * len(meaningful):
            return None
        return GestureEvent(gesture=gesture, sample=current)

    def _oldest_in_window(self, now: float, window: float) -> HandSample | None:
        cutoff = now - window
        for sample in self._history:
            if sample.t >= cutoff:
                return sample
        return None


def _first_index(values: list[float], target: float) -> int:
    return values.index(target)


def _last_index(values: list[float], target: float) -> int:
    for index in range(len(values) - 1, -1, -1):
        if values[index] == target:
            return index
    return 0


def _cell_distance(a: HandSample, b: HandSample) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
