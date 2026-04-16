from core.types import GameConfig, GameState, GameType, PlayerState

from edge.voice.intents_en import (
    VoiceIntentEN,
    apply_voice_intents_to_state,
    extract_highlight_ball_tokens,
    parse_english_intents,
)


def test_parse_trajectory_and_break_box():
    xs = parse_english_intents("Please show trajectory help")
    assert VoiceIntentEN.TRAJECTORY_ASSIST_ON in xs
    xs2 = parse_english_intents("turn off trajectory")
    assert VoiceIntentEN.TRAJECTORY_ASSIST_OFF in xs2
    assert VoiceIntentEN.SHOW_BREAK_BOX in parse_english_intents("show the break box")


def test_highlight_tokens():
    assert extract_highlight_ball_tokens("highlight the 8 and 9 balls") == ("8", "9")


def test_apply_intents_updates_layers():
    cfg = GameConfig(game_type=GameType.EIGHT_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    intents = parse_english_intents("show score and show break box")
    apply_voice_intents_to_state(st, intents)
    assert st.projector_layers.show_score is True
    assert st.projector_layers.show_break_box is True
