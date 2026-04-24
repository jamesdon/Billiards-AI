"""Unit tests for OpenCV calibration mouse → image coordinate mapping."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def calib_click_mod():
    path = ROOT / "scripts" / "calib_click.py"
    spec = importlib.util.spec_from_file_location("_calib_click_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_calib_click_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_map_highgui_mouse_identity_rect(calib_click_mod) -> None:
    f = calib_click_mod.map_highgui_mouse_to_image_xy
    assert f(640, 360, (0, 0, 1280, 720), 1280, 720) == (640, 360)


def test_map_highgui_mouse_half_scale_rect(calib_click_mod) -> None:
    f = calib_click_mod.map_highgui_mouse_to_image_xy
    assert f(320, 180, (0, 0, 640, 360), 1280, 720) == (640, 360)


def test_map_highgui_mouse_clips(calib_click_mod) -> None:
    f = calib_click_mod.map_highgui_mouse_to_image_xy
    assert f(9999, 9999, (0, 0, 1280, 720), 1280, 720) == (1279, 719)


def test_map_highgui_mouse_no_rect_uses_raw_clip(calib_click_mod) -> None:
    f = calib_click_mod.map_highgui_mouse_to_image_xy
    assert f(10, 20, None, 1280, 720) == (10, 20)
