from core.rules.straight_pool import StraightPoolRules
from core.types import Event, EventType, GameConfig, GameState, GameType, PlayerState


def test_straight_pool_ends_when_target_points_reached():
    cfg = GameConfig(game_type=GameType.STRAIGHT_POOL, straight_pool_target_points=3)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    rules = StraightPoolRules()

    st.players[0].score = 2
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=1.0))
    assert st.winner_team is None

    st.players[0].score = 3
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=2.0))
    assert st.winner_team == 0
    assert st.game_over_reason == "target_points_reached"

