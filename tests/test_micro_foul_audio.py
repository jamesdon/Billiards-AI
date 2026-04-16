from __future__ import annotations

from core.types import GameConfig, GameState, GameType, PlayerState
from edge.audio.capture import AudioRingBuffer
from edge.events.micro_foul_audio import MicroFoulAudioDetector


def test_micro_foul_stub_returns_no_events():
    st = GameState(
        config=GameConfig(game_type=GameType.EIGHT_BALL),
        players=[PlayerState("A"), PlayerState("B")],
    )
    d = MicroFoulAudioDetector(audio=AudioRingBuffer())
    d.on_shot_start(1.0)
    assert d.update(st, 2.0) == []
