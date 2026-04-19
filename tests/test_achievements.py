from core.achievements import is_successful_shot
from core.types import GameConfig, GameState, GameType, PlayerState


def test_is_successful_shot_requires_empty_fouls():
    cfg = GameConfig(game_type=GameType.STRAIGHT_POOL, num_players=2)
    st = GameState(config=cfg, players=[PlayerState(name="A"), PlayerState(name="B")])
    assert is_successful_shot(st) is True
    st.shot.fouls_this_shot.append("no_contact")
    assert is_successful_shot(st) is False
