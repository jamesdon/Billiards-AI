from core.rules.eight_ball import EightBallRules
from core.types import BallClass, BallTrack, EightBallRuleSet, Event, EventType, FoulType, GameConfig, GameState, GameType, PlayerState


def test_8ball_assigns_groups_on_first_group_pot():
    cfg = GameConfig(game_type=GameType.EIGHT_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls = {
        10: BallTrack(id=10, pos_xy=(0, 0), class_probs={BallClass.CUE: 1.0}),
        1: BallTrack(id=1, pos_xy=(0, 0), class_probs={BallClass.SOLID: 1.0}),
        9: BallTrack(id=9, pos_xy=(0, 0), class_probs={BallClass.STRIPE: 1.0}),
        8: BallTrack(id=8, pos_xy=(0, 0), class_probs={BallClass.EIGHT: 1.0}),
    }
    rules = EightBallRules()
    rules.on_event(st, Event(type=EventType.SHOT_START, ts=0.0))
    rules.on_event(st, Event(type=EventType.BALL_POCKETED, ts=0.5, payload={"ball_id": 1}))
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=1.0))
    assert st.players[0].group == BallClass.SOLID
    assert st.players[1].group == BallClass.STRIPE


def test_8ball_open_table_first_contact_with_eight_is_foul():
    cfg = GameConfig(game_type=GameType.EIGHT_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    assert st.players[0].group is None
    st.balls = {
        10: BallTrack(id=10, pos_xy=(0, 0), class_probs={BallClass.CUE: 1.0}),
        8: BallTrack(id=8, pos_xy=(0, 0), class_probs={BallClass.EIGHT: 1.0}),
    }
    st.shot.in_shot = True
    st.shot.shot_start_ts = 0.0
    st.shot.first_object_ball_hit = 8
    st.shot.rail_hits_this_shot = 1
    st.shot.pocketed_this_shot.append(99)

    rules = EightBallRules()
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=1.0))
    assert FoulType.WRONG_BALL_FIRST.value in st.shot.fouls_this_shot


def test_8ball_bar_ruleset_eight_on_break_is_rerack_not_win():
    cfg = GameConfig(game_type=GameType.EIGHT_BALL, eight_ball_ruleset=EightBallRuleSet.BAR)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls = {
        10: BallTrack(id=10, pos_xy=(0, 0), class_probs={BallClass.CUE: 1.0}),
        8: BallTrack(id=8, pos_xy=(0, 0), class_probs={BallClass.EIGHT: 1.0}),
    }
    rules = EightBallRules()
    rules.on_event(st, Event(type=EventType.SHOT_START, ts=0.0))
    rules.on_event(st, Event(type=EventType.BALL_POCKETED, ts=0.1, payload={"ball_id": 8}))
    assert st.winner_team is None
    assert st.game_over_reason == "eight_on_break_rerack"

