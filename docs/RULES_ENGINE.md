# Rules engine

## Separation of concerns

- Vision/tracking produce **ball tracks** and **physics-ish events**.
- Rules convert those events into **game state transitions**.
- Rules never depend on pixels; they depend on table-plane events.

## Interfaces

- `GameState`: authoritative state snapshot
- `RuleEngine`: deterministic transition function
- `EventProcessor`: takes low-level events and emits rule events + state deltas

## Common abstractions

- `BallId` stable per rack
- `BallLabel`: cue, eight, nine, red/yellow, snooker colors, unknown
- `Shot`: from `SHOT_START` to `SHOT_END`
- `Inning/Turn`: per player
- `PlayMode`: singles / doubles / scotch doubles
- `Team`: grouping of players used by doubles modes

## Per-game modules

- 8-ball: group assignment, win conditions, fouls
- 9-ball: lowest-first enforcement, win on 9
- straight pool: point scoring, rerack, continuation
- UK pool: red/yellow groups, black endgame
- snooker: reds/colors sequence, scoring

## League rulesets (top 3 per game)

Rules are parameterized by both **game type** and a selected **ruleset** (league/variant).

- **8-ball**: APA / BCA+WPA / Bar
- **9-ball**: WPA / APA / USAPL
- **Straight pool (14.1)**: WPA / BCA / House
- **UK pool (blackball)**: Blackball WPA / WEPF / Pub
- **Snooker**: WPBSA / IBSF / Club

## Turn rotation by play mode

- **Singles**: `next_player()` rotates to the next player.
- **Doubles**: `next_player()` rotates to the next team; shooter selection policy chooses the active player.
- **Scotch doubles**: `next_player()` rotates to the next team; within the team, shooter alternates each visit.

