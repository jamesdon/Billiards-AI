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
    assert len(d.rack_ball_centers_m) == 15
    la, lb = d.long_string
    assert abs((la[0] - lb[0]) ** 2 + (la[1] - lb[1]) ** 2) ** 0.5 - 2.84 < 0.01  # long string ~ table length
    sa, sb = d.transverse_string
    assert abs((sa[0] - sb[0]) ** 2 + (sa[1] - sb[1]) ** 2) ** 0.5 - 1.42 < 0.01  # transverse ~ table width
