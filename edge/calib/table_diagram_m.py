"""
Standard pool-table lines and points in table meters (X head→foot, Y along the head short rail).
Matches common schematic layouts: second-diamond/¼-L head and foot strings, 3 sight marks
per half between corner and side pocket on long rails, 3 between corners on short rails.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Set, Tuple

from .table_layout import head_string_x_m

Vec2 = Tuple[float, float]
Seg2 = Tuple[Vec2, Vec2]


@dataclass(frozen=True)
class TableDiagramM:
    """Geometry for a diagram overlay: strings, break box, grid, rail diamonds, side pockets, rack."""

    # Named segments (endpoints in table m)
    long_string: Seg2  # centerline down the table, length L (longer than the transverse = W)
    transverse_string: Seg2  # through side pocket centers (short centerline, parallel to head/foot)
    head_string: Seg2
    foot_string: Seg2
    break_box_m: List[Vec2]  # closed rect (4 corners) inside kitchen, centered in Y
    grid_segments: List[Seg2]  # thin reference grid
    side_pockets_m: List[Vec2]  # midpoints on long rails
    rail_diamonds_m: List[Vec2]  # sight positions on cushion lines (diamonds / sights)
    rack_ball_centers_m: List[Vec2]  # 15-ball triangle at foot, 2-1/4" centers (BCD ball size)
    captions: List[Tuple[str, Vec2]]  # (text, table-m anchor; caller projects and offsets in px)


def _u(xs: Set[float], v: float, eps: float = 1e-6) -> None:
    for x in list(xs):
        if abs(x - v) < eps:
            return
    xs.add(v)


# BCA / WPA general pocket billiards: 2-1/4" (0.05715 m) object ball; rack geometry uses centers.
_BALL_D_M: float = 2.25 * 0.0254


def fifteen_ball_rack_centers_m(table_length_m: float, table_width_m: float) -> List[Vec2]:
    """
    15-ball equilateral pack: apex (one ball) toward the head, base (five balls) toward the
    foot rail. Backs the pack off the foot cushion; ball centers use 2-1/4" spacing.
    """
    L = float(table_length_m)
    W = float(table_width_m)
    D = _BALL_D_M
    row_step = D * (math.sqrt(3.0) / 2.0)
    pack_depth = 4.0 * row_step
    rail_inset = max(2.5 * D, 0.01 * L)
    x_back = L - rail_inset
    x_apex = x_back - pack_depth
    if x_apex < 0.0:
        x_apex = 0.0
    centers: List[Vec2] = []
    for r in range(5):
        x = x_apex + r * row_step
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

    # Label anchors: corners / margins so text does not sit on the main grid and string lines.
    captions: List[Tuple[str, Vec2]] = [
        ("Head rail  TL,TR", (0.04 * L, 0.06 * W)),
        ("End rail  BL,BR", (0.80 * L, 0.06 * W)),
        ("Break box", (0.22 * hx, 0.18 * W)),
        ("Long string  (head to foot, center L)", (0.38 * L, 0.90 * W)),
        ("Transverse  (side pockets, center W)", (0.78 * L, 0.44 * W)),
        ("Head string  break line", (0.38 * hx, 0.82 * W)),
        ("Foot string", (0.5 * (ftx + L) - 0.02 * L, 0.20 * W)),
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
        captions=captions,
    )
