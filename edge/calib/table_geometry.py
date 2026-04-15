from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from core.geometry import Homography
from core.types import PocketLabel

from .calib_store import Calibration, PocketDef


@dataclass(frozen=True)
class TableGeometry:
    table_length_m: float
    table_width_m: float
    pocket_radius_m: float
    break_line_x_m: float
    break_box_x_m: float
    kitchen_line_x_m: float
    kitchen_polygon_m: List[Tuple[float, float]]


def _estimate_homography(
    image_points: List[Tuple[float, float]],
    table_length_m: float,
    table_width_m: float,
) -> np.ndarray:
    src = np.array(image_points, dtype=np.float64)
    # Expected order: TL, TR, BL, BR (physical table, not image top-left).
    # X runs head (kitchen / rack short rail) toward foot; Y runs along the head rail from TL to TR.
    L = float(table_length_m)
    W = float(table_width_m)
    dst = np.array(
        [
            [0.0, 0.0],  # TL: head + left long rail
            [0.0, W],  # TR: head + right long rail (same short rail as TL)
            [L, 0.0],  # BL: foot + left
            [L, W],  # BR: foot + right (same short rail as BL; behind break line from kitchen)
        ],
        dtype=np.float64,
    )
    A = []
    for (x, y), (X, Y) in zip(src, dst):
        A.append([-x, -y, -1.0, 0.0, 0.0, 0.0, x * X, y * X, X])
        A.append([0.0, 0.0, 0.0, -x, -y, -1.0, x * Y, y * Y, Y])
    A = np.array(A, dtype=np.float64)
    _, _, vt = np.linalg.svd(A)
    h = vt[-1].reshape(3, 3)
    if abs(float(h[2, 2])) < 1e-12:
        return h
    return h / h[2, 2]


def _default_pockets(table_length_m: float, table_width_m: float, radius_m: float) -> List[PocketDef]:
    L = float(table_length_m)
    W = float(table_width_m)
    return [
        PocketDef(PocketLabel.TOP_LEFT_CORNER, (0.0, 0.0), radius_m),
        PocketDef(PocketLabel.TOP_RIGHT_CORNER, (0.0, W), radius_m),
        PocketDef(PocketLabel.BOTTOM_LEFT_CORNER, (L, 0.0), radius_m),
        PocketDef(PocketLabel.BOTTOM_RIGHT_CORNER, (L, W), radius_m),
        PocketDef(PocketLabel.LEFT_SIDE_POCKET, (0.5 * L, 0.0), radius_m),
        PocketDef(PocketLabel.RIGHT_SIDE_POCKET, (0.5 * L, W), radius_m),
    ]


def _geometry(table_length_m: float, table_width_m: float, pocket_radius_m: float) -> TableGeometry:
    # X=0 is the head short rail (kitchen / rack). Break line is ~1/4 table length toward the foot.
    break_line_x_m = table_length_m * 0.25
    break_box_x_m = table_length_m * 0.5
    kitchen_line_x_m = break_line_x_m
    kitchen_polygon = [
        (0.0, 0.0),
        (kitchen_line_x_m, 0.0),
        (kitchen_line_x_m, table_width_m),
        (0.0, table_width_m),
    ]
    return TableGeometry(
        table_length_m=table_length_m,
        table_width_m=table_width_m,
        pocket_radius_m=pocket_radius_m,
        break_line_x_m=break_line_x_m,
        break_box_x_m=break_box_x_m,
        kitchen_line_x_m=kitchen_line_x_m,
        kitchen_polygon_m=kitchen_polygon,
    )


def auto_calibration_from_corners(
    image_points: List[Tuple[float, float]],
    table_length_m: float = 2.84,
    table_width_m: float = 1.42,
    pocket_radius_m: float = 0.07,
) -> Tuple[Calibration, TableGeometry]:
    """
    Build a calibration artifact and table geometry from 4 table corners.

    Corner order must be physical (not image top-left):
      1) TL — head rail, left long-rail corner (kitchen side)
      2) TR — head rail, right long-rail corner (same short rail as TL)
      3) BL — foot rail, left long-rail corner
      4) BR — foot rail, right long-rail corner (same short rail as BL)
    """
    if len(image_points) != 4:
        raise ValueError("image_points must contain exactly 4 corners (TL, TR, BL, BR).")
    H = _estimate_homography(image_points, table_length_m, table_width_m)
    calib = Calibration(H=Homography(H=H), pockets=_default_pockets(table_length_m, table_width_m, pocket_radius_m))
    return calib, _geometry(table_length_m, table_width_m, pocket_radius_m)


def table_geometry_dict(geom: TableGeometry) -> Dict[str, object]:
    return {
        "table_length_m": geom.table_length_m,
        "table_width_m": geom.table_width_m,
        "pocket_radius_m": geom.pocket_radius_m,
        "break_line_x_m": geom.break_line_x_m,
        "break_box_x_m": geom.break_box_x_m,
        "kitchen_line_x_m": geom.kitchen_line_x_m,
        "kitchen_polygon_m": [[x, y] for x, y in geom.kitchen_polygon_m],
    }

