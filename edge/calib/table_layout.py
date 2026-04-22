from __future__ import annotations

from typing import List, Optional, Tuple

from core.types import PocketLabel

from .calib_store import PocketDef

# **Kitchen (American pool):** the region from the **head** short rail to the **head string**
# (a/k/a break line): the imaginary line through the second diamonds (from the head) on the
# two long rails — full table width, constant x in this model. That line is the **footward**
# boundary of the kitchen; the head rail is the **headward** boundary. (Snooker/British
# “baulk / balk” is the same idea.) Cue must be in this band for a legal break (behind the
# head string, toward the head). Colloquial “bottom quarter” often means this **head** end
# of the playfield in camera view, not a geometric screen “bottom” without reference to the
# table — here x runs head→foot with TL/TR at x=0.
# **Head string** position: many tables ≈1/4 of playing **length** from the head; diamond
# spacing can vary, so 0.25 is a first-order default.
HEAD_STRING_FRACTION_OF_LENGTH: float = 0.25


def head_string_x_m(table_length_m: float) -> float:
    return float(table_length_m) * HEAD_STRING_FRACTION_OF_LENGTH


def foot_string_x_m(table_length_m: float) -> float:
    """Foot string / foot-spot line: symmetric ¼L from the foot rail (x = L)."""
    return float(table_length_m) - head_string_x_m(table_length_m)


def head_string_segment_xy_m(table_length_m: float, table_width_m: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """
    Return endpoints of the head string: from the second-diamond / width-side
    of the y=0 long rail to the y=W long rail, at x = head_string_x_m.
    """
    hx = head_string_x_m(table_length_m)
    w = float(table_width_m)
    return (hx, 0.0), (hx, w)


def head_string_segment_from_kitchen_polygon(
    kitchen_polygon_xy_m: List[Tuple[float, float]], table_width_m: float
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    Infer the head string segment from a saved kitchen rect [TL,(hx,0),(hx,W),(0,W)].
    If the polygon is missing or too short, return None.
    """
    if len(kitchen_polygon_xy_m) < 2:
        return None
    kx = float(kitchen_polygon_xy_m[1][0])
    w = float(table_width_m)
    return (kx, 0.0), (kx, w)


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
    Kitchen polygon: the quarter (along table length) between the head short rail and the head
    string, full playing width. Matches “kitchen” / “in the kitchen” for breaks and
    (bar-rule) ball-in-hand behind the string.
    """
    side = _normalize_end(head_end, default="left")
    d = head_string_x_m(table_length_m)
    w = float(table_width_m)
    if side == "left":
        return [(0.0, 0.0), (d, 0.0), (d, w), (0.0, w)]
    return [(table_length_m - d, 0.0), (table_length_m, 0.0), (table_length_m, w), (table_length_m - d, w)]


def break_area_polygon(table_length_m: float, table_width_m: float, foot_end: str = "right") -> List[Tuple[float, float]]:
    """
    **Foot-end quarter** (not the head string / break line). Optional overlay for
    “rack / foot” side heuristics — the legal break cueing region is the **kitchen**
    and the line that bounds it is the **head string** from ``head_string_segment_xy_m``.

    Nearer foot cushion: the quarter of the playing surface at the same end as the foot rail.
    """
    side = _normalize_end(foot_end, default="right")
    d = head_string_x_m(table_length_m)
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
