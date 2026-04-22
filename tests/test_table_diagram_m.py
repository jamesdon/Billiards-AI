from __future__ import annotations

from edge.calib.table_diagram_m import build_table_diagram_m


def test_table_diagram_has_head_and_foot_strings():
    d = build_table_diagram_m(2.84, 1.42)
    hx = 0.25 * 2.84
    assert abs(d.head_string[0][0] - hx) < 1e-9
    assert abs(d.foot_string[0][0] - (2.84 - hx)) < 1e-9
    assert len(d.grid_segments) > 4
    assert len(d.rail_diamonds_m) >= 12
    assert len(d.break_box_m) == 4
