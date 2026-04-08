# Test Plan

This plan is organized by major delivery phases. Each phase has:

- objective
- entry criteria
- test cases
- pass/fail gate

## Phase 1: Environment and startup

### Objective

Verify the system boots reliably on dev hardware and Jetson-style targets.

### Entry criteria

- dependencies installed
- camera available
- optional backend env vars set

### Test cases

- start edge with camera only
- start edge with ONNX model + class map
- start backend and validate `/health`
- verify MJPEG stream endpoint

### Gate

- no crashes for 15 minutes
- stable stream output

## Phase 2: Calibration and coordinate mapping

### Objective

Validate homography correctness and pocket zone alignment.

### Test cases

- load calibration JSON with all six pocket labels
- verify known table points map correctly
- confirm overlay/pocket zones visually align
- reject invalid labels/formats

### Gate

- mapping error within acceptable tolerance
- no pocket label/schema failures

## Phase 3: Detection and tracking

### Objective

Ensure robust ball/player/stick detection and ID continuity.

### Test cases

- ID stability under motion/occlusion
- re-acquisition after temporary loss
- stale track cleanup
- FPS and latency across `detect_every_n` settings

### Gate

- track continuity and runtime target met

## Phase 4: Classification and identity

### Objective

Validate ball class inference and persistent player/stick identity.

### Test cases

- cue/8/solid/stripe correctness
- UK/snooker color classes
- player profile persistence across sessions
- stick profile persistence and nickname updates

### Gate

- acceptable confusion matrix + stable profile IDs

## Phase 5: Event and foul detection

### Objective

Validate shot, collision, rail-hit, pocket, and foul outputs.

### Test cases

- `SHOT_START` / `SHOT_END`
- `BALL_COLLISION`, `RAIL_HIT`, `BALL_POCKETED`
- fouls:
  - scratch
  - wrong first contact
  - no contact
  - no rail after contact

### Gate

- event timing/order consistency and foul correctness

## Phase 6: Rules and end-of-game

### Objective

Verify ruleset-specific progression and winner selection.

### Test cases

- 8-ball: APA/BCA-WPA/bar variants
- 9-ball: WPA/APA/USAPL variants
- straight pool: target points
- UK pool and snooker end conditions
- single/doubles/scotch rotation correctness

### Gate

- winner/team/result reason matches expected outcomes

## Phase 7: Stats and analytics

### Objective

Validate shot taxonomy and numeric metrics.

### Test cases

- follow/draw distances
- cut angles
- bank/kick with rail and pocket constraints
- break-shot metrics and exclusions

### Gate

- metric ranges plausible and tag logic consistent

## Phase 8: Backend and persistence

### Objective

Verify event/state ingestion and DynamoDB persistence.

### Test cases

- shot summaries stored per player
- shot summaries stored per stick
- game-over summaries stored per player
- websocket fanout correctness
- AWS failure tolerance

### Gate

- no data loss in nominal path, graceful degradation on AWS errors

## Phase 9: End-to-end acceptance

### Objective

Run complete games and validate full stack behavior.

### Test cases

- full game per game type and ruleset
- compare final stats with manual score sheet
- confirm stored records and replayability

### Gate

- all critical flows pass without manual intervention

## Execution order

1. Phase 1-2
2. Phase 3-5
3. Phase 6-7
4. Phase 8
5. Phase 9

## Detailed runbooks

- `docs/Phase 1 Environment and startup.md`
- `docs/Phase 2 Calibration and coordinate mapping.md`
- `docs/Phase 3 Detection and tracking.md`
- `docs/Phase 4 Classification and identity.md`
- `docs/Phase 5 Event and foul detection.md`
- `docs/Phase 6 Rules and end-of-game.md`
- `docs/Phase 7 Stats and analytics.md`
- `docs/Phase 8 Backend and persistence.md`
- `docs/Phase 9 End-to-end acceptance.md`

