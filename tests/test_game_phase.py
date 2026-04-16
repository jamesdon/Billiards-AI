from edge.game_phase import VisionGamePhase, estimate_vision_game_phase


def test_phase_rack_present():
    p = estimate_vision_game_phase(rack_track_count=1, ball_track_count=12, in_shot=False)
    assert p == VisionGamePhase.RACK_PRESENT


def test_phase_open_break():
    p = estimate_vision_game_phase(rack_track_count=1, ball_track_count=5, in_shot=False)
    assert p == VisionGamePhase.OPEN_BREAK_PENDING
