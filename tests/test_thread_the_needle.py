from core.rules.straight_pool import StraightPoolRules
from core.types import BallClass, BallTrack, Event, EventType, GameConfig, GameState, GameType, PlayerState
from edge.events.thread_the_needle import ThreadTheNeedleDetector, ThreadTheNeedleConfig


def _state_two_balls() -> GameState:
    cfg = GameConfig(game_type=GameType.STRAIGHT_POOL, num_players=2)
    st = GameState(
        config=cfg,
        players=[PlayerState(name="A"), PlayerState(name="B")],
    )
    st.resolve_rotation()
    st.shot.in_shot = True
    st.shot.shot_start_ts = 0.0
    st.shot.pocketed_this_shot = [2]
    # Two balls nearly touching (sub-8 mm gap).
    st.balls[0] = BallTrack(id=0, pos_xy=(0.5, 0.5), vel_xy=(0.5, 0.0), last_seen_ts=1.0)
    st.balls[0].class_probs[BallClass.CUE] = 1.0
    st.balls[1] = BallTrack(id=1, pos_xy=(0.557, 0.5), vel_xy=(0.0, 0.0), last_seen_ts=1.0)
    st.balls[1].class_probs[BallClass.SOLID] = 1.0
    return st


def test_thread_needle_emits_after_rules_clear_fouls():
    st = _state_two_balls()
    det = ThreadTheNeedleDetector(cfg=ThreadTheNeedleConfig(max_clearance_m=0.02))
    det.on_shot_start()
    det.update(st, 1.0)
    rules = StraightPoolRules()
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=2.0))
    ev = det.try_emit_achievement(st, 2.0)
    assert ev is not None
    assert ev.payload["achievement_type"] == "thread_the_needle"
    # Counts are applied when StatsAggregator ingests ACHIEVEMENT (edge main on_event path).


def test_thread_needle_suppressed_on_foul():
    st = _state_two_balls()
    det = ThreadTheNeedleDetector(cfg=ThreadTheNeedleConfig(max_clearance_m=0.02))
    det.on_shot_start()
    det.update(st, 1.0)
    st.shot.fouls_this_shot.append("wrong_ball_first")
    rules = StraightPoolRules()
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=2.0))
    ev = det.try_emit_achievement(st, 2.0)
    assert ev is None
