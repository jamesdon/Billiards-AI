from __future__ import annotations

from edge.calib.corner_order import order_physical_table_corners, order_points_tl_tr_bl_br


def test_order_points_image_axes():
    pts = [(10.0, 10.0), (100.0, 10.0), (10.0, 100.0), (100.0, 100.0)]
    o = order_points_tl_tr_bl_br(pts)
    assert o[0] == (10.0, 10.0)
    assert o[1] == (100.0, 10.0)


def test_order_physical_is_stable():
    pts = [(0.0, 0.0), (0.0, 10.0), (10.0, 0.0), (10.0, 10.0)]
    o = order_physical_table_corners(pts)
    assert len(o) == 4
