from __future__ import annotations

import re
from dataclasses import dataclass

from frame.constants import (
    GRID_SIZE,
    HAND_MAX_MM,
    HAND_MIN_MM,
    INVALID_DISTANCE_MM,
    MAX_VALID_MM,
    MIN_VALID_MM,
    ZONE_COUNT,
)

_Y_LINE = re.compile(r"^Y(\d)\s*:\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class DepthFrame:
    """Row-major 8x8 millimetre distances. Y0 is the top row, X increases right."""

    distances_mm: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.distances_mm) != ZONE_COUNT:
            raise ValueError(f"expected {ZONE_COUNT} zones, got {len(self.distances_mm)}")

    def at(self, x: int, y: int) -> int:
        return self.distances_mm[y * GRID_SIZE + x]

    def rows(self) -> list[tuple[int, ...]]:
        return [
            self.distances_mm[y * GRID_SIZE : (y + 1) * GRID_SIZE]
            for y in range(GRID_SIZE)
        ]


def is_valid_range(mm: int) -> bool:
    return MIN_VALID_MM <= mm < INVALID_DISTANCE_MM and mm <= MAX_VALID_MM


def is_hand_range(mm: int) -> bool:
    return HAND_MIN_MM <= mm <= HAND_MAX_MM and is_valid_range(mm)


def parse_row_line(line: str) -> tuple[int, list[int]] | None:
    match = _Y_LINE.match(line.strip())
    if not match:
        return None
    y = int(match.group(1))
    if y >= GRID_SIZE:
        return None
    numbers = [int(part) for part in re.findall(r"\d+", match.group(2))]
    if len(numbers) < GRID_SIZE:
        return None
    return y, numbers[:GRID_SIZE]


def pop_usb_frames(buffer: str) -> tuple[list[DepthFrame], str]:
    """Split a live SEN0628 USB CDC stream into complete 8x8 frames.

    Firmware wraps `y0:`...`y7:` forever with CR/LF and no dashed separator.
    """
    normalized = buffer.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        complete_text, incomplete = normalized, ""
    else:
        split_at = normalized.rfind("\n")
        if split_at == -1:
            return [], normalized
        complete_text, incomplete = normalized[: split_at + 1], normalized[split_at + 1 :]

    frames: list[DepthFrame] = []
    current: dict[int, list[int]] = {}
    for line in complete_text.splitlines():
        parsed = parse_row_line(line)
        if parsed is None:
            continue
        y, values = parsed
        if y == 0:
            current = {0: values}
        elif y == len(current) and (y - 1) in current:
            current[y] = values
        else:
            current = {}
            continue
        if len(current) == GRID_SIZE:
            distances: list[int] = []
            for row_y in range(GRID_SIZE):
                distances.extend(current[row_y])
            frames.append(DepthFrame(tuple(distances)))
            current = {}

    leftover = [
        f"y{y}:" + ",".join(str(n) for n in current[y]) + ","
        for y in range(GRID_SIZE)
        if y in current
    ]
    if leftover:
        remainder = "\n".join(leftover) + "\n" + incomplete
    else:
        remainder = incomplete
    return frames, remainder


def parse_ascii_matrix(text: str) -> DepthFrame | None:
    """Parse a SEN0628 USB/serial 8x8 dump.

    Expected shape from DFRobot firmware / Arduino examples::

        Y0: 322,318,401,...
        Y1: ...
        Y7: ...
        ------------------------------
    """
    rows: dict[int, list[int]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _Y_LINE.match(line)
        if not match:
            continue
        y = int(match.group(1))
        numbers = [int(part) for part in re.findall(r"\d+", match.group(2))]
        if len(numbers) >= GRID_SIZE:
            rows[y] = numbers[:GRID_SIZE]
    if len(rows) != GRID_SIZE:
        return None
    distances: list[int] = []
    for y in range(GRID_SIZE):
        if y not in rows:
            return None
        distances.extend(rows[y])
    return DepthFrame(tuple(distances))


def parse_csv_64(text: str) -> DepthFrame | None:
    numbers = [int(part) for part in re.findall(r"\d+", text)]
    if len(numbers) < ZONE_COUNT:
        return None
    return DepthFrame(tuple(numbers[:ZONE_COUNT]))
