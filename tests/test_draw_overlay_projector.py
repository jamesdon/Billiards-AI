from __future__ import annotations

import numpy as np

from core.geometry import Homography
from core.overlay_state import ProjectorOverlayState
from core.types import GameConfig, GameState, GameType, PlayerState, PocketLabel
from edge.calib.calib_store import Calibration, PocketDef
from edge.overlay.draw import draw_overlay


def test_draw_overlay_projector_inset_smoke():
    H = np.eye(3, dtype=np.float64)
    Hp = np.array([[200.0, 0.0, 50.0], [0.0, 150.0, 30.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    calib = Calibration(
        H=Homography(H=H),
        pockets=[PocketDef(label=PocketLabel.TOP_LEFT_CORNER, center_xy_m=(0.1, 0.1), radius_m=0.06)],
        table_length_m=2.0,
        table_width_m=1.0,
        break_area_polygon_xy_m=[(0.1, 0.1), (1.9, 0.1), (1.9, 0.9), (0.1, 0.9)],
        H_projector=Homography(H=Hp),
    )
    st = GameState(
        config=GameConfig(game_type=GameType.EIGHT_BALL),
        players=[PlayerState("A"), PlayerState("B")],
    )
    st.projector_layers = ProjectorOverlayState(show_break_box=True)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    out = draw_overlay(frame, st, calib=calib)
    assert out.shape == frame.shape
    assert out.dtype == frame.dtype


def test_draw_overlay_track_debug_snapshot_smoke():
    st = GameState(
        config=GameConfig(game_type=GameType.EIGHT_BALL),
        players=[PlayerState("A"), PlayerState("B")],
    )
    setattr(
        st,
        "_track_debug_overlay",
        {
            "frame_idx": 3,
            "detector_loaded": True,
            "detector_ran": True,
            "detect_every_n": 2,
            "n_raw_dets": 1,
            "raw_count_by_label": {"ball": 1},
            "raw_detections": [
                {"label": "ball", "conf": 0.91, "bbox": (12.0, 22.0, 48.0, 58.0)},
            ],
            "n_tracks": 1,
            "track_count_by_kind": {"ball": 1, "player": 0, "stick": 0, "rack": 0},
            "boxes": [
                {"kind": "ball", "id": 1, "label": "ball", "bbox": (10.0, 20.0, 50.0, 60.0)},
            ],
        },
    )
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    out = draw_overlay(frame, st, calib=None)
    assert out.shape == frame.shape


def test_draw_overlay_without_H_projector_no_crash():
    H = np.eye(3, dtype=np.float64)
    calib = Calibration(H=Homography(H=H), pockets=[], table_length_m=2.84, table_width_m=1.42)
    st = GameState(
        config=GameConfig(game_type=GameType.EIGHT_BALL),
        players=[PlayerState("A"), PlayerState("B")],
    )
    st.projector_layers = ProjectorOverlayState(show_break_box=True)
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    out = draw_overlay(frame, st, calib=calib)
    assert out.shape == frame.shape
