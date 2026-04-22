"""
Standard pool-table lines and points in table meters (X head→foot, Y along the head short rail).
Matches common schematic layouts: second-diamond/¼-L head and foot strings, 3 sight marks
per half between corner and side pocket on long rails, 3 between corners on short rails.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Set, Tuple

from .table_layout import foot_string_x_m, head_string_x_m

Vec2 = Tuple[float, float]
Seg2 = Tuple[Vec2, Vec2]


@dataclass(frozen=True)
class TableDiagramM:
    """Geometry for a diagram overlay: strings, break box, grid, rail diamonds, side pockets, rack frames."""

    # Named segments (endpoints in table m)
    long_string: Seg2  # centerline down the table, length L (longer than the transverse = W)
    transverse_string: Seg2  # through side pocket centers (short centerline, parallel to head/foot)
    head_string: Seg2
    foot_string: Seg2
    break_box_m: List[Vec2]  # closed rect (4 corners) inside kitchen, centered in Y
    grid_segments: List[Seg2]  # thin reference grid
    side_pockets_m: List[Vec2]  # midpoints on long rails
    rail_diamonds_m: List[Vec2]  # sight positions on cushion lines (diamonds / sights)
    rack_ball_centers_m: List[Vec2]  # 15 ball centers (foot; 2-1/4" BCD) — for legacy/tests
    rack8_inner_triangle_m: List[Vec2]  # 3 corners: inner 8-ball wooden triangle (open corner toward head)
    rack9_inner_diamond_m: List[Vec2]  # 4 corners: inner 9-ball wooden diamond
    captions: List[Tuple[str, Vec2]]  # (text, table-m anchor; caller projects and offsets in px)


def _u(xs: Set[float], v: float, eps: float = 1e-6) -> None:
    for x in list(xs):
        if abs(x - v) < eps:
            return
    xs.add(v)


# BCA / WPA general pocket billiards: 2-1/4" (0.05715 m) object ball; rack geometry uses centers.
_BALL_D_M: float = 2.25 * 0.0254

# https://www.dimensions.com/element/billiards-pool-racks (inner / opening size of the rack frame)
_RACK8_INNER_BASE_M: float = 11.25 * 0.0254
_RACK8_INNER_HEAD_TO_BASE_M: float = 10.0 * 0.0254
_RACK9_INNER_DIA_ACROSS_M: float = 6.75 * 0.0254
_RACK9_INNER_DIA_ALONG_M: float = 10.0 * 0.0254


def _rack_foot_baseline_x_m(table_length_m: float) -> float:
    """
    Inset from foot cushion (x = L) where the back row of balls sits (15-ball pack depth check).
    """
    L = float(table_length_m)
    rail_inset = max(2.5 * _BALL_D_M, 0.01 * L)
    return L - float(rail_inset)


def eight_nine_rack_outlines_m(table_length_m: float, table_width_m: float) -> Tuple[List[Vec2], List[Vec2]]:
    """
    Return inner wooden rack outlines: 8-ball triangle (3 verts), 9-ball rhombus (4 verts).

    Sizes from https://www.dimensions.com/element/billiards-pool-racks (inner opening):
    eight-ball 11.25\" × 10\", nine-ball 6.75\" × 10\".

    Apex / lead ball sits on the **foot string** (¼L from foot rail), opening toward the head.
    """
    L = float(table_length_m)
    W = float(table_width_m)
    ftx = foot_string_x_m(L)
    half_b = 0.5 * _RACK8_INNER_BASE_M
    y_lo = 0.5 * W - half_b
    y_hi = 0.5 * W + half_b
    x_open = min(ftx + _RACK8_INNER_HEAD_TO_BASE_M, L - 1e-4)
    tri8: List[Vec2] = [(float(x_open), float(y_lo)), (float(x_open), float(y_hi)), (float(ftx), 0.5 * W)]

    half_a = 0.5 * _RACK9_INNER_DIA_ALONG_M
    half_c = 0.5 * _RACK9_INNER_DIA_ACROSS_M
    x_back = min(ftx + 2.0 * half_a, L - 1e-4)
    d9: List[Vec2] = [
        (float(ftx), 0.5 * W),
        (float(ftx + half_a), 0.5 * W + half_c),
        (float(x_back), 0.5 * W),
        (float(ftx + half_a), 0.5 * W - half_c),
    ]
    return tri8, d9


def fifteen_ball_rack_centers_m(table_length_m: float, table_width_m: float) -> List[Vec2]:
    """
    15-ball equilateral pack: apex ball on the **foot string** (foot spot line), rows toward the
    foot rail; 2-1/4\" ball-center spacing (BCA).
    """
    L = float(table_length_m)
    W = float(table_width_m)
    D = _BALL_D_M
    row_step = D * (math.sqrt(3.0) / 2.0)
    foot_x = foot_string_x_m(L)
    centers: List[Vec2] = []
    for r in range(5):
        x = foot_x - float(r) * row_step
        if x < 0.0:
            x = 0.0
        n = r + 1
        for j in range(n):
            y = 0.5 * W + (j - 0.5 * (n - 1)) * D
            centers.append((float(x), float(y)))
    return centers


def build_table_diagram_m(table_length_m: float, table_width_m: float) -> TableDiagramM:
    L = float(table_length_m)
    W = float(table_width_m)
    hx = head_string_x_m(L)
    ftx = L - hx  # foot string, ¼L from foot rail

    # --- Strings (infinite lines as table segments) ---
    long_a: Vec2 = (0.0, 0.5 * W)
    long_b: Vec2 = (L, 0.5 * W)
    tsv_a: Vec2 = (0.5 * L, 0.0)  # “center” line through both side pockets
    tsv_b: Vec2 = (0.5 * L, W)
    hs_a: Vec2 = (hx, 0.0)
    hs_b: Vec2 = (hx, W)
    fs_a: Vec2 = (ftx, 0.0)
    fs_b: Vec2 = (ftx, W)

    # --- Break box (WPA-style: in kitchen, centered on transverse, width between 2nd/3rd head-rail sight regions) ---
    y_lo = 0.25 * W
    y_hi = 0.75 * W
    break_box: List[Vec2] = [(0.0, y_lo), (hx, y_lo), (hx, y_hi), (0.0, y_hi)]

    # --- Long-rail sight marks: 3 between corner and side pocket (each ½-long side) × 2 rails ---
    long_diamonds_x: List[float] = []
    for a, b in ((0.0, 0.5 * L), (0.5 * L, L)):
        d = b - a
        for k in (1, 2, 3):
            long_diamonds_x.append(a + d * (k / 4.0))  # 1/4, 1/2, 3/4 of the half, i.e. L/8, L/4, 3L/8 and +L/2
    # Short-rail: 3 between corner pockets
    head_foot_diamonds_y: List[float] = [0.25 * W, 0.5 * W, 0.75 * W]

    rail_diamonds: List[Vec2] = []
    for xm in long_diamonds_x:
        rail_diamonds.append((float(xm), 0.0))
        rail_diamonds.append((float(xm), W))
    for ym in head_foot_diamonds_y:
        rail_diamonds.append((0.0, float(ym)))
        rail_diamonds.append((L, float(ym)))
    # Dedupe
    seen: Set[Tuple[int, int]] = set()
    uniq: List[Vec2] = []
    for x, y in rail_diamonds:
        k = (int(round(x * 1e6)), int(round(y * 1e6)))
        if k in seen:
            continue
        seen.add(k)
        uniq.append((x, y))
    rail_diamonds = uniq

    # --- Grid: all distinct verticals/horizontals at string + diamond x/y ---
    x_set: Set[float] = set()
    for x in list(long_diamonds_x) + [hx, 0.5 * L, ftx, 0.0, L]:
        _u(x_set, float(x))
    y_set: Set[float] = set()
    for y in head_foot_diamonds_y + [0.0, W, 0.5 * W]:
        _u(y_set, float(y))

    grid: List[Seg2] = []
    for x in sorted(x_set):
        if 0.0 <= x <= L:
            grid.append(((x, 0.0), (x, W)))
    for y in sorted(y_set):
        if 0.0 < y < W:  # avoid double-tracing the outer frame (corners are drawn)
            grid.append(((0.0, y), (L, y)))

    side_s: List[Vec2] = [(0.5 * L, 0.0), (0.5 * L, W)]
    rack_centers: List[Vec2] = fifteen_ball_rack_centers_m(L, W)
    tri8, dia9 = eight_nine_rack_outlines_m(L, W)

    # Label anchors (table m): sit beside the feature they name, not on top of lines.
    break_box_cx = 0.5 * hx
    break_box_cy = 0.5 * (y_lo + y_hi)
    x_rack = _rack_foot_baseline_x_m(L) - 0.12 * L
    captions: List[Tuple[str, Vec2]] = [
        ("Head rail", (0.02 * L, 0.5 * W)),
        ("End rail", (L - 0.02 * L, 0.5 * W)),
        ("Break box", (break_box_cx, break_box_cy)),
        ("Long string", (0.48 * L, 0.5 * W + 0.065 * W)),
        ("Transverse", (0.5 * L, 0.36 * W)),
        ("Head string", (hx - 0.065 * L, 0.5 * W)),
        ("Break line", (hx + 0.065 * L, 0.5 * W)),
        ("Foot string", (ftx + 0.065 * L, 0.5 * W)),
        ("8: inner 11.25 x 10 in triangle", (max(0.02 * L, x_rack), 0.72 * W)),
        ("9: inner 6.75 x 10 in diamond", (max(0.02 * L, x_rack - 0.04 * L), 0.62 * W)),
    ]

    return TableDiagramM(
        long_string=(long_a, long_b),
        transverse_string=(tsv_a, tsv_b),
        head_string=(hs_a, hs_b),
        foot_string=(fs_a, fs_b),
        break_box_m=break_box,
        grid_segments=grid,
        side_pockets_m=side_s,
        rail_diamonds_m=rail_diamonds,
        rack_ball_centers_m=rack_centers,
        rack8_inner_triangle_m=tri8,
        rack9_inner_diamond_m=dia9,
        captions=captions,
    )
