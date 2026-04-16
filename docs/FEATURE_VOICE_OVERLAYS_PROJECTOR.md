# Feature: voice, overlays, and overhead projector

## Voice (English first, i18n later)

- **Baseline**: `edge/voice/intents_en.py` maps **normalized English text** (from future ASR) to `VoiceIntentEN` enums.
- **Production path**: microphone → ASR (e.g. Whisper small / streaming) → `parse_english_intents(text)` → `apply_voice_intents_to_state(...)`.
- **On-device today**: `--voice-line` / `--voice-phrases-file` on `edge.main`; optional PCM via `--mic-device` with `--enable-audio-micro-foul` (`sounddevice` in `requirements-audio.txt`) feeds `AudioRingBuffer` for upcoming micro-foul fusion (no ASR in-process yet).
- **Internationalization**: add sibling modules (`intents_es.py`, …) and a locale router; keep intent enums stable across languages.

### Trajectory vs overlays

- **Trajectory assist** phrases toggle `GameState.trajectory_assist_enabled` (see `docs/FEATURE_TRAJECTORY_PREDICTION.md`).
- **Projector layer** phrases toggle `GameState.projector_layers` (`core/overlay_state.py`) — independent toggles.

## Projector layers (voice / UI)

`ProjectorOverlayState` fields (all default **hidden** until asked):

| # | Layer | Field |
|---|--------|--------|
| 1 | Break box | `show_break_box` |
| 2 | Break string / kitchen edge | `show_break_string` |
| 3 | Score | `show_score` |
| 4 | My stats | `show_my_stats` |
| 5 | Best next shot | `show_best_next_shot` |
| 6 | Alternative next shot | `show_alt_next_shot` + `alt_shot_variant_index` (cycle on repeated “another option”) |
| 7 | Highlight ball(s) | `highlighted_ball_labels` (e.g. `("8","cue")`) |

Rendering uses **inverse homography** (`Homography.to_pixel`) to map table polygons onto the camera frame for preview; the **same** table coordinates feed a **second** warp for the overhead projector (homography per display — store `H_table_to_projector` when calibrated).

## Hardware connection

- Jetson Orin Nano → HDMI (or USB-C DP) → projector.
- Align **projector intrinsics** once: calibrate `H_table_to_projector` using four known table corners (similar to cloth homography, different target plane).

## AR / “best shot” solvers

`show_best_next_shot` / `show_alt_next_shot` are **hooks**; plug in a shot planner (rules-aware or pure physics) as a separate module so voice/UI does not entangle with `EightBallRules` internals.
