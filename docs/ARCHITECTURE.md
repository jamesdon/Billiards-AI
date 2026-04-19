# System architecture

## Goals

- Detect billiard balls in real time from a live camera feed on constrained edge hardware.
- Track balls across frames with stable IDs and trajectories.
- Classify ball type (color, stripe/solid, number if visible) across different sets.
- Detect events: pocketing, collisions, fouls, shot completion.
- Maintain full game state and support multiple game types via a pluggable rule engine.
- Provide real-time overlay + streaming; optionally offload heavier processing to backend.

## High-level architecture

```text
Camera/Video -> Detection -> Tracking -> Classification -> Motion/Events -> Rules -> GameState
      |            |            |            |               |           |
      +--> Overlay/Stream <-----+------------+---------------+-----------+
      +--> (Optional) Backend: state/events upload + persistence + dashboards
```

### Trajectory vs rules (product split)

Two **independent** feature lines share state but not code ownership:

| Track | Responsibility | Doc |
|-------|----------------|-----|
| **Trajectory prediction** | Path history, aim / rollout overlays, shooter-opt-in via voice | `docs/FEATURE_TRAJECTORY_PREDICTION.md` |
| **Real-time rules** | Fouls, turns, scoring — pure `Event` → `GameState` | `docs/FEATURE_REALTIME_RULES.md` |

**Voice + projector** layers (`docs/FEATURE_VOICE_OVERLAYS_PROJECTOR.md`) toggle `projector_layers` and `trajectory_assist_enabled` without changing rules internals.

**Vision game phase** (`docs/FEATURE_GAME_PHASE_VISION.md`) adds rack/ball-count heuristics for UX; rules remain authoritative.

**Audio** for micro-fouls: `docs/HARDWARE_IMX477_AUDIO.md`.

## Play modes (applies to all game types)

- **Singles**: 1v1. Turn rotates between players.
- **Doubles**: 2v2. Turn rotates between **teams**; a configurable “team shooter policy” chooses which teammate shoots (baseline: team captain).
- **Scotch doubles**: 2v2. Turn rotates between teams and the shooter **alternates within the team** each visit.

The rules engine is game-type specific, but **turn/inning bookkeeping** is shared and driven by play mode.

## Player + cue stick detection (identity)

In addition to balls, the vision layer can optionally detect:

- **players** (person silhouettes)
- **cue sticks** (long thin objects near cue ball / players)

The edge pipeline maintains a lightweight **identity layer**:

- Extract an **appearance signature** (baseline: HSV color histogram) from each player/stick ROI.
- Match against locally stored profiles to assign a stable `profile_id`.
- Allow custom naming (e.g., “Jordan”, “House Cue #2”) and persist for future games.

### Edge-first philosophy

The edge pipeline is designed to run *fully standalone* on Jetson Orin Nano (JetPack 5.x class hardware):

- **Detector** runs as ONNXRuntime (baseline) or TensorRT (optimized).
- **Tracker** is lightweight IoU/velocity association by default (no embedding model).
- **Classifier** uses fast HSV-based heuristics; number OCR is optional.
- **Event detection** uses table coordinates and kinematic signals.
- **Rules engine** is pure-Python, with deterministic state transitions.

### Optional backend offload

If enabled, the edge device publishes:

- `FrameSummary` (balls, velocities, state snapshot at low rate)
- `Event` stream (shot start/stop, pocket, collision, foul)

Backend responsibilities:

- persist history (SQLite/Postgres)
- aggregate statistics
- multi-camera fusion (future)
- dashboards (web UI)

## Data flow (per frame)

1. Acquire frame + timestamp.
2. Run detector at adaptive rate \(f_{det}\) (not necessarily every frame).
3. Postprocess detections: NMS + coordinate conversion.
4. Associate detections to tracks; update track states (position/velocity history).
5. Classify each tracked ball using cropped ROI + temporal smoothing.
6. Transform pixel coordinates to **table coordinates** via homography calibration.
7. Compute motion metrics (velocity, acceleration) and infer:
   - cue strike
   - collisions
   - pocketing
   - shot start/stop
8. Send events into rules engine to update game state.
9. Render overlay + optionally stream.

## Coordinate systems

- **Pixel coords**: \((x, y)\) in image space.
- **Table coords (meters)**: \((X, Y)\) on the table plane after homography.
- **Pocket zones**: polygons/circles defined in table coords.

Calibration is described in `docs/CALIBRATION.md`.

## Performance model

Key knobs for Orin Nano (same ideas apply to other Jetson-family boards; Orin has more headroom):

- detector input size (default letterbox 640×640; must match exported ONNX)
- detector interval (e.g., every 2–3 frames)
- crop size for classification (small)
- overlay resolution (can be lower than capture)
- cap stream FPS (e.g., 15)

## Failure modes and mitigation

- **ID switches**: mitigated by table-plane association + velocity gating.
- **Occlusion**: keep tracks alive briefly; re-identify by nearest plausible position.
- **False pocketing**: require disappearance near pocket zone for \(T_{miss}\) frames.
- **Wrong-first contact**: computed from first collision at shot start (rule-aware).

