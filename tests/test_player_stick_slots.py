from __future__ import annotations

from core.identity_store import IdentityStore
from core.types import GameConfig, GameState, GameType, PlayerState, PlayerProfile
from edge.classify.player_stick_id import PlayerStickIdentifier


def test_assign_profile_prefers_left_right_slots_for_two_players(tmp_path):
    store = IdentityStore(str(tmp_path / "id.json"))
    ident = PlayerStickIdentifier(store=store)
    cfg = GameConfig(game_type=GameType.EIGHT_BALL, num_players=2)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])

    left_prof = PlayerProfile(id="left-id", display_name="L", color_signature=[0.1] * 256)
    ident.assign_profile_to_players(st, left_prof, center_x_px=100.0, frame_width_px=800)
    assert st.players[0].profile_id == "left-id"

    right_prof = PlayerProfile(id="right-id", display_name="R", color_signature=[0.2] * 256)
    ident.assign_profile_to_players(st, right_prof, center_x_px=600.0, frame_width_px=800)
    assert st.players[1].profile_id == "right-id"


def test_assign_profile_skips_when_profile_already_seated(tmp_path):
    store = IdentityStore(str(tmp_path / "id2.json"))
    ident = PlayerStickIdentifier(store=store)
    cfg = GameConfig(game_type=GameType.EIGHT_BALL, num_players=2)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.players[0].profile_id = "same"
    st.players[0].name = "Seated"
    prof = PlayerProfile(id="same", display_name="X", color_signature=[0.3] * 256)
    ident.assign_profile_to_players(st, prof, center_x_px=700.0, frame_width_px=800)
    assert st.players[1].profile_id is None
