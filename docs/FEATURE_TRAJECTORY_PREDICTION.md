# Feature: trajectory prediction (isolated)

## Purpose

**Trajectory prediction** answers *where the cue ball (and optionally object balls) are going* — aim lines, post-contact path history, and simple forward extrapolation. It is **not** the rules engine: it does not decide fouls, legal first hits, or game phase.

## Relationship to real-time rules

- **Input**: tracked ball state, table geometry, optional stick pose, shooter-enabled flag.
- **Output**: polylines / meshes for projector and broadcast overlays.
- **Rules** consume the same `GameState` and `Event` stream independently; see `docs/FEATURE_REALTIME_RULES.md`.

At **gameplay time**, the default UX is:

1. Shooter **asks verbally** for trajectory help (English first; other locales later — see `docs/FEATURE_VOICE_OVERLAYS_PROJECTOR.md`).
2. `GameState.trajectory_assist_enabled` becomes `true` (voice layer).
3. After **stick–cue-ball contact** (existing `SHOT_START` / collision heuristics), the UI shows:
   - **Historical** cue path (table coordinates, last N seconds).
   - **Parallel channel**: outputs from **real-time rules** (e.g. “open table”, “first hit was legal”) without merging logic into the trajectory module.

## Code map (scaffolding)

- `edge/trajectory/assist.py` — `TrajectoryAssistController` (history + stub projection).
- `edge/voice/intents_en.py` — toggles `trajectory_assist_enabled` from parsed English phrases.
- Future: rail–cushion integrator, spin model, multi-ball propagation.

## Wiring (edge)

- `EdgePipeline` holds one `TrajectoryAssistController`. On each `SHOT_START` event it calls `on_shot_start` (clears history). While `trajectory_assist_enabled` is true, every frame calls `append_cue_sample` and stores polylines on `GameState` as `_traj_history_table_m` / `_traj_projection_table_m` for `draw_overlay` (camera pixels via table homography `H`).
- `edge.main` can toggle layers from `--voice-line` or `--voice-phrases-file` (mtime-based re-read); no ASR in-process yet.

## Non-goals

- Do not fold foul detection into trajectory math.
- Do not block the MJPEG/rules pipeline on heavy physics; trajectory may run at lower rate or on a second thread.
