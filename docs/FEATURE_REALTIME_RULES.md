# Feature: real-time rules (isolated)

## Purpose

The **rules engine** (`core/rules/*`) consumes **events** (`SHOT_START`, `BALL_COLLISION`, `FOUL`, `SHOT_END`, …) and mutates **`GameState`** deterministically. It must **not** depend on trajectory prediction, projector layers, or voice parsing.

## Contract

- **Inputs**: `Event` stream + current `GameState`.
- **Outputs**: updated `GameState`, optional new `Event`s (e.g. synthetic fouls from base rules).
- **No imports** from `edge/trajectory/`, `edge/voice/`, or projector overlay code.

## After cue contact (broadcast UX)

When the shooter enables trajectory help, the **display** may show:

1. Trajectory module output (path history + projection).
2. **Rules summary** for the same interval (e.g. wrong-ball-first at `SHOT_END`) — two **parallel** readouts from the same state/events, composed only in the overlay / projector layer.

## Micro-fouls and audio

Referee-grade signals (double hit, push, etc.) extend **event detection** and optional **audio** correlation; see `docs/HARDWARE_IMX477_AUDIO.md`. Those detectors emit **normal** `Event`s / reasons consumed here — still not merged into trajectory code.
