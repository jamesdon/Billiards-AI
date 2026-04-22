from __future__ import annotations

from edge.calib.table_layout import (
    HEAD_STRING_FRACTION_OF_LENGTH,
    break_area_polygon,
    head_string_segment_from_kitchen_polygon,
    head_string_segment_xy_m,
)


def test_head_string_is_across_table_not_along_head_rail():
    L, W = 2.84, 1.42
    a, b = head_string_segment_xy_m(L, W)
    assert abs(a[0] - b[0]) < 1e-9  # same x (across the table)
    assert a[0] == L * HEAD_STRING_FRACTION_OF_LENGTH
    assert a[1] == 0.0 and b[1] == W  # y runs along the head rail (TL to TR)
    # Not the first edge of the kitchen (that would be a segment of the long rail, dy=0):
    assert abs(a[1] - b[1]) > 0.1


def test_kitchen_foot_from_saved_rect():
    L, W = 2.0, 1.0
    kx = 0.25 * L
    k = [
        (0.0, 0.0),
        (kx, 0.0),
        (kx, W),
        (0.0, W),
    ]
    seg = head_string_segment_from_kitchen_polygon(k, W)
    assert seg is not None
    assert seg == ((kx, 0.0), (kx, W))


def test_foot_quarter_width_about_quarter_length():
    L, W = 2.84, 1.42
    fq = break_area_polygon(L, W)
    xs = [p[0] for p in fq]
    # Foot quarter spans ~0.25*L in x (not half-table).
    assert abs((max(xs) - min(xs)) - 0.25 * L) < 1e-6
