# Event detection

This layer converts trajectories into semantic events consumed by the rules engine.

## Events

- `SHOT_START`, `SHOT_END`
- `BALL_POCKETED`
- `BALL_COLLISION`
- `CUE_STRIKE`
- `FOUL` (scratch/no-contact/wrong-first; rule-dependent)
- `PLAYER_TURN_BEGIN`, `PLAYER_TURN_OVER` — **turn** boundaries (one or more shots until the rules pass the table). Emitted by the edge runtime when rotation changes after `SHOT_END`, plus an opening `PLAYER_TURN_BEGIN` at session start. Payload: `player_idx`, `team_idx`, `name`, `profile_id`. Not produced by the physics detectors.

- `PLAYER_SHOT_BEGIN`, `PLAYER_SHOT_OVER` — **single stroke** boundaries (one cue motion until balls rest). Emitted with each `SHOT_START` / `SHOT_END` from the pipeline (before rules consume `SHOT_END`). `PLAYER_SHOT_BEGIN` includes `seconds_since_previous_shot_over` (gap since the last `PLAYER_SHOT_OVER`, or `null` for the first stroke). `PLAYER_SHOT_OVER` includes `shot_duration_s`. Use the gap for **shot clock** (time between end of table motion and next stroke).

- `ACHIEVEMENT` — extensible stream; `payload["achievement_type"]` uses `AchievementType` in `core/types.py` (e.g. `thread_the_needle`). Counts accumulate on `PlayerState.achievement_counts` on the edge when stats ingest the event. **Achievements are only evaluated for successful strokes** (no fouls on the shot; see `is_successful_shot` in `core/achievements.py`), after rules finish processing `SHOT_END`.

## Shot analytics vs `ACHIEVEMENT` events

Per-shot **kinematic** labels (e.g. `bank`, `cut`) live on **`shot_summary`** from `edge/events/shot_analyzer.py`. Separately, **`ACHIEVEMENT`** events (see `AchievementType` in `core/types.py`) carry session-level feats such as **`thread_the_needle`** with counts on `PlayerState.achievement_counts` via `core/stats.py`.

| Source | What it represents |
|--------|---------------------|
| `ShotTag` enum in `core/types.py` | Labels on each `ShotSummary`: `stun`, `follow`, `draw`, `cut`, `thread_the_needle`, `bank`, `kick`, `combination`, `jump`, `masse`, `english`, `carom`, `break`. |
| `ShotSummary` fields | `tags`, `follow_distance_m`, `draw_distance_m`, `cut_angle_deg`, `break_rail_hits`, `break_pocketed`, `rail_hits_by_ball`, `cue_peak_speed_mps`, shooter/stick profile IDs, etc. |
| `AchievementType` + `ACHIEVEMENT` events | Named feats (`thread_the_needle`, …); extend the enum and emit from `edge/events/` detectors. |
| `core/stats.py` (`StatsAggregator`) | Ball speeds, cue peak speed, last shot duration, **`achievement_counts` on `PlayerState`** when processing `ACHIEVEMENT`. |
| `backend/aws_store.py` | Persists **`shot_summary`** rows per player/stick profile when the backend ingests events (optional DynamoDB). |

To tune “bank” vs other tags, adjust `ShotAnalyzerConfig` and `edge/events/shot_analyzer.py`. For **`thread_the_needle`**, tune `ThreadTheNeedleConfig` in `edge/events/thread_the_needle.py`. Add new achievement types by extending `AchievementType`, implementing a detector under `edge/events/`, and emitting `ACHIEVEMENT` after rules when appropriate.

#### `thread_the_needle` (achievement)

During each shot, `ThreadTheNeedleDetector` tracks the **minimum surface clearance** (m) between moving balls and between balls and cushions. After `RuleEngine` finishes on `SHOT_END`, if clearance stayed below `max_clearance_m`, at least one **object** ball was pocketed, and the shot has **no** fouls, the runtime emits `ACHIEVEMENT` with `achievement_type=thread_the_needle` and increments `PlayerState.achievement_counts["thread_the_needle"]`. The stroke also receives `ShotTag.thread_the_needle` on `shot_summary` when eligible.

## Shot detection

Heuristic baseline:

- Shot starts when cue-ball acceleration exceeds threshold and kinetic energy increases.
- Shot ends when all balls are below a speed threshold for \(T_{rest}\) seconds.

This is robust even without cue stick detection.

## Pocket detection

- Define pocket zones in table coordinates (circles/polygons).
- A ball is pocketed when:
  - it disappears (track lost) for \(\ge N\) frames
  - its last known position was inside a pocket zone (with margin)
  - its speed was non-trivial in the preceding frames (optional)

## Collision detection

Between balls A and B at time t:

- If distance \(\le d_{contact}\) and either:
  - relative velocity changes abruptly, or
  - both velocities change direction in a correlated way
then emit `BALL_COLLISION(A, B)`.

The **first** collision after shot start is used by rules for “wrong ball first”.

## Fouls

The foul detector is **rule-aware**:

- Scratch: cue ball pocketed.
- No-contact: no collision event involving cue ball after shot start.
- Wrong-first: first object ball hit is illegal per game type.
- No rail after contact: if no ball is pocketed and no rail is touched after legal contact.

### Expanded foul taxonomy

#### Technical and shot-based

- Cue ball scratch / off table
- Wrong ball first
- No contact
- No rail after contact
- Double hit / push shot (sensor-limited; currently manual/review)
- Balls still moving before stroke (sensor-limited; currently manual/review)
- Jump shot infraction / scoop (rule and sensor dependent)

#### Physical and conduct

- Touched ball (manual/review)
- No foot on floor (manual/review)
- Bad cue ball placement on ball-in-hand (requires placement region logic)
- Unsportsmanlike conduct (manual/admin)

### Penalty model by game family

- American pool (8/9/14.1/UK pool): foul gives opponent ball-in-hand.
- Snooker: foul gives penalty points to opponent (minimum 4 by default; ball-dependent in advanced implementation).
- Carom billiards: point deduction + inning end (planned; not yet active because carom game type is not currently implemented).

