# API + streaming schemas (edge ↔ backend)

## Transport options

- **WebSocket (JSON)**: common for dashboards and real-time state.
- **HTTP REST (JSON)**: configuration + history queries.
- **MQTT (optional)**: common IoT/event bus for constrained networks.
- **gRPC (optional)**: efficient binary RPC; best in controlled deployments.

Baseline implementation will use **WebSocket + REST**.

## Edge message types

### `StateSnapshot`

- `ts`: float (seconds)
- `game`: game config + play mode + teams
- `players`: list (current scores/fouls/innings)
- `balls`: list (id, class, pos, vel)
- `shot`: in_shot, shooter, peak speeds

### `Event`

- `type`: string
- `ts`: float
- `payload`: dict

Includes:

- pocketing: `{ ball_id, pocket_label }`
- collision: `{ a, b }`
- foul: `{ reason, team_idx, player_idx }`
- identity: `{ profile_id, display_name }`
- profile rename: `PATCH /profiles/player/{id}` or `PATCH /profiles/stick/{id}`
- turn boundaries: `type="player_turn_begin"` / `type="player_turn_over"` with `{ player_idx, team_idx, name, profile_id }` (rotation after a shot ends, plus an opening `player_turn_begin` at session start)
- shot boundaries: `type="player_shot_begin"` / `type="player_shot_over"` with `{ player_idx, team_idx, name, profile_id }` plus `seconds_since_previous_shot_over` on begin and `shot_duration_s` on over (shot-clock gap between strokes)
- achievements: `type="achievement"` with `{ achievement_type, player_idx, team_idx, name, profile_id, ... }` (e.g. `thread_the_needle` with `min_clearance_m`)
- game over: edge emits `type="game_over"` with `{ winner_team, game_over_reason, rulesets, final scores }`
- rack detected: edge emits `type="rack_detected"` with `{ confidence, bbox_xyxy, fallback_reason }`
- manual foul injection: `POST /fouls/manual` with `{ game_type, foul_type, player_idx/team_idx, notes, foul_points? }`
- live reducer state: `GET /live/state`
- reset live reducer: `POST /live/reset`

WebSocket also broadcasts `type="live_state"` whenever events/states are ingested.

