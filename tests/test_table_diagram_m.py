from __future__ import annotations

from edge.calib.table_diagram_m import build_table_diagram_m
from edge.calib.table_layout import foot_string_x_m


def test_table_diagram_has_head_and_foot_strings():
    d = build_table_diagram_m(2.84, 1.42)
    hx = 0.25 * 2.84
    assert abs(d.head_string[0][0] - hx) < 1e-9
    assert abs(d.foot_string[0][0] - (2.84 - hx)) < 1e-9
    assert len(d.grid_segments) > 4
    assert len(d.rail_diamonds_m) >= 12
    assert len(d.break_box_m) == 4
    assert len(d.rack_ball_centers_m) == 15
    assert len(d.rack8_inner_triangle_m) == 3
    assert len(d.rack9_inner_diamond_m) == 4
    # dimensions.com: 8 inner 11.25" (base) x 10" (apex to base)
    yb = abs(d.rack8_inner_triangle_m[0][1] - d.rack8_inner_triangle_m[1][1])
    assert abs(yb - 11.25 * 0.0254) < 0.01
    xa = abs(d.rack8_inner_triangle_m[0][0] - d.rack8_inner_triangle_m[2][0])
    assert abs(xa - 10.0 * 0.0254) < 0.01
    la, lb = d.long_string
    assert abs((la[0] - lb[0]) ** 2 + (la[1] - lb[1]) ** 2) ** 0.5 - 2.84 < 0.01  # long string ~ table length
    sa, sb = d.transverse_string
    assert abs((sa[0] - sb[0]) ** 2 + (sa[1] - sb[1]) ** 2) ** 0.5 - 1.42 < 0.01  # transverse ~ table width


def test_fifteen_ball_rack_apex_on_foot_string():
    L, W = 2.84, 1.42
    d = build_table_diagram_m(L, W)
    fx = foot_string_x_m(L)
    apex = d.rack_ball_centers_m[0]
    assert abs(apex[0] - fx) < 1e-6
    assert abs(apex[1] - 0.5 * W) < 1e-9


def test_centered_placeholder_aspect_ratio():
    from edge.calib.table_geometry import centered_table_placeholder_corners_px

    tl, tr, bl, br = centered_table_placeholder_corners_px(1000, 500, 2.84, 1.42)
    long_px = bl[0] - tl[0]
    short_px = tr[1] - tl[1]
    # Long rail along image +x, head rail along image +y → long_px / short_px = L / W.
    assert abs((long_px / short_px) - (2.84 / 1.42)) < 0.01
    assert long_px > short_px + 1e-6
    cx = 0.25 * (tl[0] + tr[0] + bl[0] + br[0])
    cy = 0.25 * (tl[1] + tr[1] + bl[1] + br[1])
    assert abs(cx - 500.0) < 1.0
    assert abs(cy - 250.0) < 1.0
