from __future__ import annotations

from core.types import GameConfig, GameState, GameType, PlayerState, PlayMode


def test_singles_next_player_wrap_increments_inning():
    cfg = GameConfig(game_type=GameType.EIGHT_BALL, play_mode=PlayMode.SINGLES, num_players=2)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.resolve_rotation()
    assert st.current_player_idx == 0
    assert st.inning == 1
    st.next_player()
    assert st.current_player_idx == 1
    assert st.inning == 1
    st.next_player()
    assert st.current_player_idx == 0
    assert st.inning == 2


def test_doubles_next_player_rotates_teams_and_picks_captain():
    cfg = GameConfig(
        game_type=GameType.EIGHT_BALL,
        play_mode=PlayMode.DOUBLES,
        num_players=4,
        teams=[[0, 1], [2, 3]],
    )
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B"), PlayerState("C"), PlayerState("D")])
    st.resolve_rotation()
    assert st.current_team_idx == 0
    assert st.current_player_idx == 0
    st.next_player()
    assert st.current_team_idx == 1
    assert st.current_player_idx == 2
    st.next_player()
    assert st.current_team_idx == 0
    assert st.current_player_idx == 0
    assert st.inning == 2


def test_scotch_doubles_advance_within_team_swaps_shooter():
    cfg = GameConfig(
        game_type=GameType.EIGHT_BALL,
        play_mode=PlayMode.SCOTCH_DOUBLES,
        num_players=4,
        teams=[[0, 1], [2, 3]],
    )
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B"), PlayerState("C"), PlayerState("D")])
    st.resolve_rotation()
    st.current_team_idx = 0
    st.current_player_idx = 0
    st.advance_within_team()
    assert st.current_player_idx == 1
    st.advance_within_team()
    assert st.current_player_idx == 0
