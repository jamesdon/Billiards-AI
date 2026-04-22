"""
Order four image points as physical table corners TL, TR, BL, BR for homography.
Shared by calibration UIs and pocket-detection heuristics.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np


def order_points_tl_tr_bl_br(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = np.array(points, dtype=np.float64)
    if pts.shape[0] < 4:
        raise ValueError("Need at least 4 points to order corners.")
    s = pts.sum(axis=1)
    diff = pts[:, 0] - pts[:, 1]
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(diff)]
    bl = pts[np.argmin(diff)]
    return [(float(p[0]), float(p[1])) for p in (tl, tr, br, bl)]


def _order_physical_table_corners_impl(
    points: List[Tuple[float, float]],
    *,
    head_toward_small_image_y: bool,
) -> List[Tuple[float, float]]:
    pts = np.array(points, dtype=np.float64)
    if pts.shape[0] != 4:
        raise ValueError("Need exactly 4 corners.")
    c = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    order = np.argsort(angles)
    p = pts[order]
    p0, p1, p2, p3 = p[0], p[1], p[2], p[3]

    def dist(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    len01 = dist(p0, p1)
    len12 = dist(p1, p2)
    len23 = dist(p2, p3)
    len30 = dist(p3, p0)
    sum_a = len01 + len23
    sum_b = len12 + len30

    def mid(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return 0.5 * (a + b)

    def head_is_first_short_pair(p_a: np.ndarray, p_b: np.ndarray, p_c: np.ndarray, p_d: np.ndarray) -> bool:
        m01 = float(mid(p_a, p_b)[1])
        m23 = float(mid(p_c, p_d)[1])
        return (m01 <= m23) if head_toward_small_image_y else (m01 >= m23)

    if sum_a <= sum_b:
        if head_is_first_short_pair(p0, p1, p2, p3):
            head_a, head_b = p0, p1
            foot_a, foot_b = p2, p3
        else:
            head_a, head_b = p2, p3
            foot_a, foot_b = p0, p1
    else:
        if head_is_first_short_pair(p1, p2, p3, p0):
            head_a, head_b = p1, p2
            foot_a, foot_b = p3, p0
        else:
            head_a, head_b = p3, p0
            foot_a, foot_b = p1, p2

    if float(head_a[0]) <= float(head_b[0]):
        tl, tr = head_a, head_b
    else:
        tl, tr = head_b, head_a
    if float(foot_a[0]) <= float(foot_b[0]):
        bl, br = foot_a, foot_b
    else:
        bl, br = foot_b, foot_a
    return [
        (float(tl[0]), float(tl[1])),
        (float(tr[0]), float(tr[1])),
        (float(bl[0]), float(bl[1])),
        (float(br[0]), float(br[1])),
    ]


def order_physical_table_corners(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Order four detected corners as physical TL, TR, BL, BR.

    TL and TR share the head short rail (kitchen / rack). BL and BR share the foot short rail.
    """
    if len(points) != 4:
        raise ValueError("Need exactly 4 corners.")
    flat = [(float(x), float(y)) for x, y in points]
    img_ref = order_points_tl_tr_bl_br(flat)
    phys_lo = _order_physical_table_corners_impl(flat, head_toward_small_image_y=True)
    phys_hi = _order_physical_table_corners_impl(flat, head_toward_small_image_y=False)

    def _match_cost(phys: List[Tuple[float, float]]) -> float:
        return float(
            sum(
                (phys[i][0] - img_ref[i][0]) ** 2 + (phys[i][1] - img_ref[i][1]) ** 2
                for i in range(4)
            )
        )

    return phys_lo if _match_cost(phys_lo) <= _match_cost(phys_hi) else phys_hi
