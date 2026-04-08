# Event detection

This layer converts trajectories into semantic events consumed by the rules engine.

## Events

- `SHOT_START`, `SHOT_END`
- `BALL_POCKETED`
- `BALL_COLLISION`
- `CUE_STRIKE`
- `FOUL` (scratch/no-contact/wrong-first; rule-dependent)

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

