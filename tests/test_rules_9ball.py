from core.rules.nine_ball import NineBallRules
from core.types import (
    BallClass,
    BallTrack,
    Event,
    EventType,
    GameConfig,
    GameState,
    GameType,
    NineBallRuleSet,
    PlayerState,
)


def test_9ball_wrong_first_contact_is_foul_and_turn_passes():
    cfg = GameConfig(game_type=GameType.NINE_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls = {
        1: BallTrack(id=1, pos_xy=(0, 0), number=1, class_probs={BallClass.UNKNOWN: 1.0}),
        2: BallTrack(id=2, pos_xy=(0, 0), number=2, class_probs={BallClass.UNKNOWN: 1.0}),
        10: BallTrack(id=10, pos_xy=(0, 0), number=None, class_probs={BallClass.CUE: 1.0}),
    }
    rules = NineBallRules()
    rules.on_event(st, Event(type=EventType.SHOT_START, ts=0.0))
    # cue hits 2 first (illegal; lowest is 1)
    st.shot.first_object_ball_hit = 2
    rules.on_event(st, Event(type=EventType.SHOT_END, ts=1.0))
    assert st.players[0].fouls == 1
    assert st.current_player_idx == 1


def test_9ball_three_fouls_loss_in_wpa_ruleset():
    cfg = GameConfig(game_type=GameType.NINE_BALL, nine_ball_ruleset=NineBallRuleSet.WPA)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls = {
        1: BallTrack(id=1, pos_xy=(0, 0), number=1, class_probs={BallClass.UNKNOWN: 1.0}),
        2: BallTrack(id=2, pos_xy=(0, 0), number=2, class_probs={BallClass.UNKNOWN: 1.0}),
        10: BallTrack(id=10, pos_xy=(0, 0), number=None, class_probs={BallClass.CUE: 1.0}),
    }
    rules = NineBallRules()
    for i in range(3):
        rules.on_event(st, Event(type=EventType.SHOT_START, ts=float(i)))
        st.shot.first_object_ball_hit = 2  # illegal each time
        rules.on_event(st, Event(type=EventType.SHOT_END, ts=float(i) + 0.5))
        # keep same shooter for consecutive-foul scenario in this synthetic test
        st.current_player_idx = 0
        st.current_team_idx = 0
    assert st.winner_team == 1
    assert st.game_over_reason == "three_consecutive_fouls"

