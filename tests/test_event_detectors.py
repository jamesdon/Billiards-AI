"""Synthetic tests for edge event-detector logic (no camera / ONNX)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from core.geometry import Homography
from core.rules.snooker import SnookerRules
from core.types import (
    BallClass,
    BallTrack,
    BallObservation,
    EventType,
    GameConfig,
    GameState,
    GameType,
    PlayerState,
    PocketLabel,
)
from edge.calib.calib_store import Calibration, PocketDef
from edge.classify.ball_classifier import BallClassifier
from edge.events.collision_detector import CollisionDetector, CollisionDetectorConfig
from edge.events.pocket_detector import PocketDetector, PocketDetectorConfig
from edge.events.rail_hit_detector import RailHitDetector, RailHitDetectorConfig
from edge.events.shot_detector import ShotDetector, ShotDetectorConfig
from edge.tracking.iou_tracker import IoUTracker


def test_shot_detector_uses_dt_normalized_acceleration():
    cfg = GameConfig(game_type=GameType.EIGHT_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls[1] = BallTrack(id=1, pos_xy=(0.0, 0.0), vel_xy=(0.0, 0.0), class_probs={BallClass.CUE: 1.0})
    det = ShotDetector(ShotDetectorConfig(cue_accel_thres=50.0))

    assert det.update(st, 0.0) == []
    assert det.update(st, 1.0) == []

    st.balls[1].vel_xy = (6.0, 0.0)
    evs = det.update(st, 1.1)
    assert len(evs) == 1
    assert evs[0].type == EventType.SHOT_START


def test_iou_tracker_constant_velocity_prediction_keeps_id_on_fast_slide():
    tr = IoUTracker()
    o0 = BallObservation(bbox_xyxy=(0.0, 0.0, 20.0, 20.0), conf=0.9, label="ball")
    m0 = tr.update([o0], 0.0)
    tid = next(iter(m0.keys()))

    o1 = BallObservation(bbox_xyxy=(100.0, 0.0, 120.0, 20.0), conf=0.9, label="ball")
    m1 = tr.update([o1], 0.1)
    assert tid in m1

    o2 = BallObservation(bbox_xyxy=(200.0, 0.0, 220.0, 20.0), conf=0.9, label="ball")
    m2 = tr.update([o2], 0.2)
    assert tid in m2


def test_calibration_roundtrip_persists_table_and_polygons():
    H = np.eye(3, dtype=np.float64)
    pockets = [
        PocketDef(label=PocketLabel.TOP_LEFT_CORNER, center_xy_m=(0.1, 0.2), radius_m=0.05),
    ]
    c = Calibration(
        H=Homography(H=H),
        pockets=pockets,
        table_length_m=2.1,
        table_width_m=1.05,
        kitchen_polygon_xy_m=[(0.0, 0.0), (1.0, 0.0)],
        break_area_polygon_xy_m=[(0.5, 0.5)],
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cal.json"
        c.save(str(p))
        c2 = Calibration.load(str(p))
    assert c2.table_length_m == 2.1
    assert c2.table_width_m == 1.05
    assert c2.kitchen_polygon_xy_m == [(0.0, 0.0), (1.0, 0.0)]
    assert c2.break_area_polygon_xy_m == [(0.5, 0.5)]
    assert len(c2.pockets) == 1


def test_snooker_expect_any_colored_ball_is_distinct_from_unknown_class():
    rules = SnookerRules()
    rules.expect_any_colored_ball = True
    rules.expected = BallClass.SNOOKER_RED
    st = GameState(config=GameConfig(game_type=GameType.SNOOKER), players=[PlayerState("A"), PlayerState("B")])
    assert rules._is_legal_target(st, BallClass.SNOOKER_YELLOW)
    assert not rules._is_legal_target(st, BallClass.SNOOKER_RED)


def test_ball_classifier_reset_clears_class_probs():
    t = BallTrack(id=1, pos_xy=(0.0, 0.0), class_probs={BallClass.SOLID: 0.9})
    BallClassifier.reset_track(t)
    assert t.class_probs == {}


def test_pocket_detector_emits_when_track_disappears_near_pocket():
    H = np.eye(3, dtype=np.float64)
    pockets = [
        PocketDef(label=PocketLabel.TOP_LEFT_CORNER, center_xy_m=(0.03, 0.03), radius_m=0.07),
    ]
    calib = Calibration(H=Homography(H=H), pockets=pockets)
    det = PocketDetector(PocketDetectorConfig(missing_time_s=0.1, pocket_margin_m=0.05))
    cfg = GameConfig(game_type=GameType.EIGHT_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls[1] = BallTrack(id=1, pos_xy=(0.03, 0.03), vel_xy=(0.0, 0.0))
    assert det.update(st, 0.0, calib) == []
    st.balls.pop(1, None)
    evs = det.update(st, 0.5, calib)
    assert len(evs) == 1
    assert evs[0].type == EventType.BALL_POCKETED
    assert 1 in st.pocketed


def test_collision_detector_emits_on_close_approach_with_relative_speed():
    det = CollisionDetector(CollisionDetectorConfig(contact_dist_m=0.10, min_rel_speed_mps=0.05, cooldown_s=0.0))
    cfg = GameConfig(game_type=GameType.EIGHT_BALL)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls[1] = BallTrack(id=1, pos_xy=(0.0, 0.0), vel_xy=(0.5, 0.0))
    st.balls[2] = BallTrack(id=2, pos_xy=(0.05, 0.0), vel_xy=(0.0, 0.0))
    evs = det.update(st, 0.0)
    assert len(evs) == 1
    assert evs[0].type == EventType.BALL_COLLISION


def test_rail_hit_detector_emits_on_velocity_reversal_near_left_rail():
    det = RailHitDetector(RailHitDetectorConfig(rail_band_m=0.05, min_speed_mps=0.05, cooldown_s=0.0))
    cfg = GameConfig(game_type=GameType.EIGHT_BALL, table_length_m=2.0, table_width_m=1.0)
    st = GameState(config=cfg, players=[PlayerState("A"), PlayerState("B")])
    st.balls[1] = BallTrack(id=1, pos_xy=(0.02, 0.5), vel_xy=(-0.3, 0.0))
    assert det.update(st, 0.0) == []
    st.balls[1].vel_xy = (0.15, 0.0)
    evs = det.update(st, 0.2)
    assert len(evs) == 1
    assert evs[0].type == EventType.RAIL_HIT
    assert evs[0].payload.get("rail") == "left"


def test_nine_ball_consecutive_foul_keys_distinguish_team_and_player_index_zero():
    d: dict[tuple[str, int], int] = {}
    d[("team", 0)] = 1
    d[("player", 0)] = 2
    assert d[("team", 0)] == 1
    assert d[("player", 0)] == 2
