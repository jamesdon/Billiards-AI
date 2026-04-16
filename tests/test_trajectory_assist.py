from __future__ import annotations

from core.types import BallClass, BallTrack, GameConfig, GameState, GameType, PlayerState
from edge.trajectory.assist import TrajectoryAssistController


def test_on_shot_start_clears_history():
    st = GameState(
        config=GameConfig(game_type=GameType.EIGHT_BALL),
        players=[PlayerState("A"), PlayerState("B")],
    )
    st.balls[1] = BallTrack(id=1, pos_xy=(1.0, 0.5), vel_xy=(0.0, 0.0), class_probs={BallClass.CUE: 1.0})
    c = TrajectoryAssistController()
    c.append_cue_sample(0.0, st)
    assert len(c.history_polyline_table_m()) == 1
    c.on_shot_start(0.1, 1)
    assert c.history_polyline_table_m() == []


def test_clear_method():
    st = GameState(
        config=GameConfig(game_type=GameType.EIGHT_BALL),
        players=[PlayerState("A"), PlayerState("B")],
    )
    st.balls[1] = BallTrack(id=1, pos_xy=(1.0, 0.5), vel_xy=(0.0, 0.0), class_probs={BallClass.CUE: 1.0})
    c = TrajectoryAssistController()
    c.append_cue_sample(0.0, st)
    c.clear()
    assert c.history_polyline_table_m() == []
