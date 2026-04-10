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
    # Expected order: TL, TR, BL, BR.
    dst = np.array(
        [
            [0.0, 0.0],
            [table_length_m, 0.0],
            [0.0, table_width_m],
            [table_length_m, table_width_m],
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
    return [
        PocketDef(PocketLabel.TOP_LEFT_CORNER, (0.0, 0.0), radius_m),
        PocketDef(PocketLabel.TOP_RIGHT_CORNER, (table_length_m, 0.0), radius_m),
        PocketDef(PocketLabel.BOTTOM_LEFT_CORNER, (0.0, table_width_m), radius_m),
        PocketDef(PocketLabel.BOTTOM_RIGHT_CORNER, (table_length_m, table_width_m), radius_m),
        PocketDef(PocketLabel.LEFT_SIDE_POCKET, (0.0, table_width_m * 0.5), radius_m),
        PocketDef(PocketLabel.RIGHT_SIDE_POCKET, (table_length_m, table_width_m * 0.5), radius_m),
    ]


def _geometry(table_length_m: float, table_width_m: float, pocket_radius_m: float) -> TableGeometry:
    # Break line is roughly 1/4 table length from the head string side.
    break_line_x_m = table_length_m * 0.25
    break_box_x_m = table_length_m * 0.5
    # Kitchen is the quarter-table nearest the breaking side in this coordinate convention.
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

    Corner order must be:
      1) top-left
      2) top-right
      3) bottom-left
      4) bottom-right
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

