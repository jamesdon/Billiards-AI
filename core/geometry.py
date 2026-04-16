from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

import numpy as np


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def bbox_center_xy(bbox_xyxy: Tuple[float, float, float, float]) -> Tuple[float, float]:
    x1, y1, x2, y2 = bbox_xyxy
    return ((x1 + x2) * 0.5, (y1 + y2) * 0.5)


def l2(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return float((dx * dx + dy * dy) ** 0.5)


@dataclass(frozen=True)
class Homography:
    H: np.ndarray  # 3x3

    def to_table(self, xy_px: Tuple[float, float]) -> Tuple[float, float]:
        x, y = xy_px
        p = np.array([x, y, 1.0], dtype=np.float64)
        q = self.H @ p
        if abs(float(q[2])) < 1e-9:
            return (0.0, 0.0)
        return (float(q[0] / q[2]), float(q[1] / q[2]))

    def batch_to_table(self, pts_px: Iterable[Tuple[float, float]]) -> np.ndarray:
        pts = np.array([[x, y, 1.0] for x, y in pts_px], dtype=np.float64).T  # 3xN
        q = self.H @ pts
        q[:2, :] /= (q[2:3, :] + 1e-9)
        return q[:2, :].T

    def to_pixel(self, xy_m: Tuple[float, float]) -> Tuple[float, float]:
        """Map table-plane meters → pixel coordinates (inverse homography)."""
        H_inv = np.linalg.inv(self.H)
        x, y = xy_m
        p = np.array([x, y, 1.0], dtype=np.float64)
        q = H_inv @ p
        if abs(float(q[2])) < 1e-9:
            return (0.0, 0.0)
        return (float(q[0] / q[2]), float(q[1] / q[2]))

