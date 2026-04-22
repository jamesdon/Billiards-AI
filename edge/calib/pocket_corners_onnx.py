"""
Optional: derive calibration quad corners from YOLO `pockets` class detections.

Six real pocket openings in view → the convex hull of det centers is the four corner
pockets; side pocket centers sit inside the quadrilateral.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, TYPE_CHECKING

import cv2
import numpy as np

from .corner_order import order_physical_table_corners

if TYPE_CHECKING:
    from edge.vision.detector_onnxruntime import OnnxRuntimeDetector

Vec2 = Tuple[float, float]


def _bbox_center_xyxy(bbox: Tuple[float, float, float, float]) -> Vec2:
    x1, y1, x2, y2 = bbox
    return (0.5 * (x1 + x2), 0.5 * (y1 + y2))


def corners_from_pocket_detections(
    frame_bgr: np.ndarray,
    detector: "OnnxRuntimeDetector",
    class_label: str = "pockets",
    min_conf: float = 0.2,
) -> Optional[List[Vec2]]:
    """
    Return four image-space corners in physical order TL, TR, BL, BR if
    the convex hull of `pockets` det centers is a quadrilateral (exactly 4 vertices).
    """
    obs = detector.detect(frame_bgr, 0.0)
    hits: List[Vec2] = []
    for o in obs:
        if str(o.label) != str(class_label):
            continue
        if float(o.conf) < float(min_conf):
            continue
        x1, y1, x2, y2 = o.bbox_xyxy
        hits.append(_bbox_center_xyxy((x1, y1, x2, y2)))
    if len(hits) < 4:
        return None
    pts = np.array(hits, dtype=np.float32).reshape((-1, 1, 2))
    hull = cv2.convexHull(pts)
    if hull is None:
        return None
    hflat = hull.reshape(-1, 2)
    if hflat.shape[0] != 4:
        return None
    flat = [(float(p[0]), float(p[1])) for p in hflat]
    return order_physical_table_corners(flat)
