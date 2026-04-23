# Phase 6: Rules and end-of-game

## Goal

Validate per-game and per-ruleset end-of-game outcomes.

## 1) Run automated rules tests

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
pytest -q "/home/$USER/Billiards-AI/tests/test_rules_8ball.py" "/home/$USER/Billiards-AI/tests/test_rules_9ball.py" "/home/$USER/Billiards-AI/tests/test_end_of_game_straight_pool.py"
```

## 2) Manual end-of-game event validation

Start backend:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8780
```

Inject synthetic game-over:

```bash
curl -s -X POST "http://127.0.0.1:8780/event" \
  -H "Content-Type: application/json" \
  -d '{
    "type":"game_over",
    "ts": 1710000000.0,
    "payload":{
      "game_type":"8ball",
      "play_mode":"singles",
      "rulesets":{"8ball":"apa","9ball":"wpa","straight_pool":"wpa","uk_pool":"blackball_wpa","snooker":"wpbsa"},
      "winner_team":0,
      "game_over_reason":"eight_ball_pocketed_legally",
      "inning":4,
      "shot_count":28,
      "players":[{"name":"A","profile_id":"p1","score":0,"fouls":1,"shots_taken":14,"innings":4},{"name":"B","profile_id":"p2","score":0,"fouls":2,"shots_taken":14,"innings":4}],
      "teams":[{"name":"A","player_indices":[0],"score":0,"fouls":1,"innings":4},{"name":"B","player_indices":[1],"score":0,"fouls":2,"innings":4}]
    }
  }'
```

Check live state:

```bash
curl -s "http://127.0.0.1:8780/live/state"
```

## Pass criteria

- tests pass
- live reducer shows winner/rulesets/reason correctly

