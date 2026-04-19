from core.rules.straight_pool import StraightPoolRules
from core.rules.turn_events import initial_player_turn_begin_event, player_turn_events_after_shot_end
from core.types import Event, EventType, GameConfig, GameState, GameType, PlayerState


def _minimal_state() -> GameState:
    cfg = GameConfig(game_type=GameType.STRAIGHT_POOL, num_players=2)
    st = GameState(
        config=cfg,
        players=[
            PlayerState(name="A"),
            PlayerState(name="B"),
        ],
    )
    st.resolve_rotation()
    return st


def test_initial_player_turn_begin_payload():
    st = _minimal_state()
    ev = initial_player_turn_begin_event(st, ts=1.0)
    assert ev.type == EventType.PLAYER_TURN_BEGIN
    assert ev.payload["player_idx"] == 0
    assert ev.payload["name"] == "A"


def test_turn_rotates_after_miss_no_score_straight_pool():
    st = _minimal_state()
    rules = StraightPoolRules()
    rules.on_event(st, Event(type=EventType.SHOT_START, ts=0.0))
    before_p, before_t = st.current_player_idx, st.current_team_idx
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=1.0))
    assert st.current_player_idx == 1
    evs = player_turn_events_after_shot_end(st, before_p, before_t, 1.0)
    assert len(evs) == 2
    assert evs[0].type == EventType.PLAYER_TURN_OVER
    assert evs[0].payload["player_idx"] == 0
    assert evs[1].type == EventType.PLAYER_TURN_BEGIN
    assert evs[1].payload["player_idx"] == 1


def test_no_turn_events_when_same_player_continues_after_pocket():
    st = _minimal_state()
    rules = StraightPoolRules()
    rules.on_event(st, Event(type=EventType.SHOT_START, ts=0.0))
    rules.on_event(st, Event(type=EventType.BALL_POCKETED, ts=0.5, payload={"ball_id": 1}))
    before_p, before_t = st.current_player_idx, st.current_team_idx
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=1.0))
    evs = player_turn_events_after_shot_end(st, before_p, before_t, 1.0)
    assert evs == []
