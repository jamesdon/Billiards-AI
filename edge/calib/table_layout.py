from __future__ import annotations

from typing import List, Tuple

from core.types import PocketLabel

from .calib_store import PocketDef


def _normalize_end(end: str, default: str) -> str:
    e = str(end).strip().lower()
    if e in ("left", "head"):
        return "left"
    if e in ("right", "foot"):
        return "right"
    # Legacy aliases occasionally used in docs/notes.
    if e in ("top",):
        return "left"
    if e in ("bottom",):
        return "right"
    return default


def kitchen_polygon(table_length_m: float, table_width_m: float, head_end: str = "left") -> List[Tuple[float, float]]:
    """
    Kitchen area polygon in table coordinates.

    Baseline definition: quarter-table nearest the head end.
    """
    side = _normalize_end(head_end, default="left")
    d = float(table_length_m) * 0.25
    w = float(table_width_m)
    if side == "left":
        return [(0.0, 0.0), (d, 0.0), (d, w), (0.0, w)]
    return [(table_length_m - d, 0.0), (table_length_m, 0.0), (table_length_m, w), (table_length_m - d, w)]


def break_area_polygon(table_length_m: float, table_width_m: float, foot_end: str = "right") -> List[Tuple[float, float]]:
    """
    Break area polygon in table coordinates.

    Baseline definition: quarter-table nearest the foot end.
    """
    side = _normalize_end(foot_end, default="right")
    d = float(table_length_m) * 0.25
    w = float(table_width_m)
    if side == "left":
        return [(0.0, 0.0), (d, 0.0), (d, w), (0.0, w)]
    return [(table_length_m - d, 0.0), (table_length_m, 0.0), (table_length_m, w), (table_length_m - d, w)]


def infer_table_size_from_pockets(pockets: List[PocketDef]) -> Tuple[float, float]:
    """
    Infer table length/width from standard pocket centers.

    Falls back to 9ft defaults if required labels are missing.
    """
    by_label = {p.label: p for p in pockets}
    try:
        tl = by_label[PocketLabel.TOP_LEFT_CORNER].center_xy_m
        tr = by_label[PocketLabel.TOP_RIGHT_CORNER].center_xy_m
        bl = by_label[PocketLabel.BOTTOM_LEFT_CORNER].center_xy_m
    except KeyError:
        return 2.84, 1.42
    # X is head-to-foot; Y is along the head rail (TL–TR).
    length = abs(float(bl[0]) - float(tl[0]))
    width = abs(float(tr[1]) - float(tl[1]))
    if length <= 0.0 or width <= 0.0:
        return 2.84, 1.42
    return length, width
