from __future__ import annotations

from backend.reducer import LiveGameReducer


def test_reducer_tracks_shot_lifecycle_and_physics_events():
    r = LiveGameReducer()
    r.state["players"] = [{"name": "A", "fouls": 0, "score": 0}, {"name": "B", "fouls": 0, "score": 0}]

    r.ingest_event({"type": "shot_start", "ts": 1.0, "payload": {"current_player_idx": 0}})
    assert r.state["in_shot"] is True
    assert r.state["rail_hits_this_shot"] == 0

    r.ingest_event({"type": "rail_hit", "ts": 1.05, "payload": {"ball_id": 3, "rail": "left"}})
    assert r.state["rail_hits_this_shot"] == 1
    assert r.state["recent_rail_hits"][-1]["rail"] == "left"

    r.ingest_event({"type": "ball_collision", "ts": 1.06, "payload": {"a": 1, "b": 2}})
    assert r.state["recent_collisions"][-1]["a"] == 1

    r.ingest_event({"type": "ball_pocketed", "ts": 1.07, "payload": {"ball_id": 2, "pocket_label": "top_left_corner"}})
    assert r.state["recent_ball_pockets"][-1]["ball_id"] == 2

    r.ingest_event({"type": "shot_end", "ts": 2.0, "payload": {"current_player_idx": 1, "inning": 2}})
    assert r.state["in_shot"] is False
    assert r.state["shot_count"] == 1
    assert r.state["current_player_idx"] == 1
    assert r.state["inning"] == 2


def test_reducer_ingest_state_merges_rotation_fields():
    r = LiveGameReducer()
    r.ingest_state(
        {
            "ts": 10.0,
            "inning": 3,
            "shot_count": 7,
            "current_player_idx": 1,
            "current_team_idx": 0,
            "ball_in_hand_for_team": 1,
            "in_shot": False,
            "players": [{"name": "A"}],
            "teams": [],
        }
    )
    assert r.state["inning"] == 3
    assert r.state["shot_count"] == 7
    assert r.state["current_player_idx"] == 1
    assert r.state["ball_in_hand_for_team"] == 1
