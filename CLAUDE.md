# frame

Gesture-controlled digital photo frame: scan a media library, Ken Burns / motion playback (browser preview today, LED matrix target), and control via DFRobot SEN0628 8×8 ToF over USB serial.

Human-oriented setup and commands live in `README.md`. This file is for agents and reviewers: conventions, boundaries, and the review ladder.

## Tiered Review Ladder (plans AND implementation)

Reviews progress cheapest → most expensive; the most expensive tier is always the **final** pass, never the first:

1. **Sonnet — exploration / first pass.** Codebase exploration, small implementations, first-pass QAQC and architecture scan.
2. **Opus — senior review & refinement.** Validates and corrects the sonnet pass; tightens design and edge cases.
3. **Fable — engineering-manager approval.** Final gate on **both** the plan (before implementation) and the merge verdict (after QA). Fable never implements; approval does **not** authorize merge — the human merges.

Every review round includes at minimum **QAQC** (correctness, regressions) and **Architecture** (module boundaries, blast radius). Add specialists proportional to the change:

| Specialist | When |
|------------|------|
| **embedded-io** | Serial/USB (`sensor.py`, `matrix.py`), firmware flash, port probing, timing on the 8×8 stream |
| **image-pipeline** | Library pairing (`library.py`), derive/cache (`derive.py`, Pillow, ffmpeg), cache invalidation |
| **preview-ux** | `frame/web/` and preview HTTP API (`preview.py`) — layout, gestures reflected in UI |

**Recursive until approved.** Findings → fix → re-submit to the **same** tier; repeat until approved, max **3 cycles** per tier, then escalate to the human with open findings. Fixes after the last review round are unreviewed — do not merge without re-review.

**Right-size depth.** Docs-only → no committee. Mechanical, single-module tweaks → sonnet + one opus pass. Serial protocol, gesture thresholds, derive write path, or slideshow state → full ladder + Fable gate.

**Closure = prove command.** Ship a re-runnable check in the PR/issue body; re-run at merge. Default prove for this repo:

```bash
python3 -m frame.selftest
```

## Layout

- `frame/` — Python package (all runtime logic).
- `frame/web/` — Static preview UI served by `preview.py`.
- `firmware/` — Bundled SEN0628 UF2 for recovery.
- `assets/` — Demo, labeled test GIFs, and generated validation corpus.

## Critical patterns

**Constants and schema.** Sensor tuning → `frame/constants.py`. File suffixes, skip rules, cache dir names, motion kind strings → `frame/schema.py`. Do not scatter magic strings.

**Library → derive → player.** `scan_library` / `pair_assets` produce `MediaAsset` lists. `build_slides` writes into per-library `.frame-cache` (see `storage.cache_dir_for`) and returns `Slide` objects. `Slideshow` owns playback state and gesture commands only — no Pillow or serial I/O inside `player.py`.

**Threading.** `Slideshow` uses an internal lock; preview and breadboard run sensor readers on background threads and call `slideshow.apply_gesture` / tick APIs from those threads. Keep new shared state behind the same lock or immutable message passing.

**Gestures.** `matrix.py` parses USB ASCII into `DepthFrame`; `GestureClassifier` in `gestures.py` consumes frames and emits `Gesture` enums. Threshold changes belong in `constants.py` with coverage in `selftest.py`.

**Hardware path.** `UsbMatrixSensor` reads CDC at `BAUD_RATE`; use `discover.py` / `python -m frame --probe` for port diagnosis. Mac dev uses USB; Pi runtime is intended to reuse the same serial stack.

**Caches.** Derived stills/motion live under `<library>/.frame-cache/` (name from `schema.CACHE_DIR_NAME`). Token keys come from `derive.asset_token` — change pairing or derive rules with cache invalidation in mind.

**CLI entry points.** `python -m frame` → `breadboard.py`. Preview, library scan, flash, discover, and selftest are separate `python -m frame.<module>` modules (see README).

## Code philosophy

Prefer simplifying and extending existing modules over parallel implementations. New behavior should be testable without hardware (`selftest.py`); add cases there when fixing parser, pairing, or gesture edge bugs.

Agents do not push, merge, or deploy unless the human explicitly asks. Commit with hooks when the task requires it.
