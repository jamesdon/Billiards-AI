# Feature: explicit game phase from vision

## Goal

Infer **where we are in the match setup** from detections (rack, ball count, optional break box), complementary to the **rules** state machine.

## Baseline

- `edge/game_phase.py` — `VisionGamePhase` enum and `estimate_vision_game_phase(...)`.
- Inputs: **rack** track count (from `rack` class), **ball** track count, `shot.in_shot`.
- Outputs: coarse phases such as `RACK_PRESENT`, `OPEN_BREAK_PENDING`, `IN_PROGRESS`.

## Roadmap (Roboflow-style parity)

1. **Rack + head string**: detect rack triangle + cue in kitchen / outside break box (calibration polygons in `Calibration.break_area_polygon_xy_m` / `kitchen_polygon_xy_m`).
2. **Legal break setup**: all balls behind head string except cue placement rules (league-specific).
3. **Post-break**: rack absent + balls moving → `IN_PROGRESS`.

## Integration

- Edge pipeline may attach `vision_phase` to UI / logging; **rules** remain authoritative for fouls and scoring.
- When phase transitions are confident, emit optional `EventType` extensions or structured logs for analytics.
