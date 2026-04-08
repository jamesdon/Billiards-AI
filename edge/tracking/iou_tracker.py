from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.geometry import bbox_center_xy
from core.types import BallId, BallObservation


def iou_xyxy(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-9)


@dataclass
class IoUTrackerConfig:
    iou_match_thres: float = 0.2
    max_age_s: float = 0.5


@dataclass
class IoUTracker:
    """
    Very lightweight tracker for edge:
    - Greedy IoU association
    - Keeps IDs stable when detections are consistent

    This is the fallback when ByteTrack/DeepSORT would be too heavy.
    """

    cfg: IoUTrackerConfig = IoUTrackerConfig()
    _next_id: int = 1
    _tracks_px: Dict[BallId, Tuple[Tuple[float, float, float, float], float]] = field(default_factory=dict)

    def update(
        self, dets: List[BallObservation], ts: float
    ) -> Dict[BallId, Tuple[Tuple[float, float], Tuple[float, float, float, float], str]]:
        # returns mapping of track_id -> (pixel center, bbox_xyxy, label)
        assigned: Dict[BallId, Tuple[Tuple[float, float], Tuple[float, float, float, float], str]] = {}
        used_det = set()

        # associate existing tracks
        for tid, (tbbox, tts) in list(self._tracks_px.items()):
            if ts - tts > self.cfg.max_age_s:
                del self._tracks_px[tid]
                continue
            best_iou = 0.0
            best_j = -1
            for j, d in enumerate(dets):
                if j in used_det:
                    continue
                v = iou_xyxy(tbbox, d.bbox_xyxy)
                if v > best_iou:
                    best_iou = v
                    best_j = j
            if best_j >= 0 and best_iou >= self.cfg.iou_match_thres:
                d = dets[best_j]
                used_det.add(best_j)
                self._tracks_px[tid] = (d.bbox_xyxy, ts)
                assigned[tid] = (bbox_center_xy(d.bbox_xyxy), d.bbox_xyxy, d.label)

        # create new tracks
        for j, d in enumerate(dets):
            if j in used_det:
                continue
            tid = self._next_id
            self._next_id += 1
            self._tracks_px[tid] = (d.bbox_xyxy, ts)
            assigned[tid] = (bbox_center_xy(d.bbox_xyxy), d.bbox_xyxy, d.label)

        return assigned

