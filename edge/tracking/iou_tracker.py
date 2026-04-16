from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.geometry import bbox_center_xy, l2
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


def _shift_bbox_xyxy(
    bbox: Tuple[float, float, float, float], dx: float, dy: float
) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


@dataclass
class IoUTrackerConfig:
    iou_match_thres: float = 0.2
    max_age_s: float = 0.5
    # When IoU(pred_bbox, det) is weak (e.g. first frame after a large jump), allow association
    # if detection center is within this distance (px) of the predicted center.
    center_match_max_dist_px: float = 120.0


@dataclass
class IoUTracker:
    """
    Very lightweight tracker for edge:
    - Greedy IoU association with constant-velocity bbox prediction (px/s)
    - Keeps IDs stable when detections are consistent

    This is the fallback when ByteTrack/DeepSORT would be too heavy.
    """

    cfg: IoUTrackerConfig = field(default_factory=IoUTrackerConfig)
    _next_id: int = 1
    # track_id -> (bbox_xyxy, last_update_ts, vel_x_px_s, vel_y_px_s)
    _tracks_px: Dict[BallId, Tuple[Tuple[float, float, float, float], float, float, float]] = field(
        default_factory=dict
    )

    def update(
        self, dets: List[BallObservation], ts: float
    ) -> Dict[BallId, Tuple[Tuple[float, float], Tuple[float, float, float, float], str]]:
        # returns mapping of track_id -> (pixel center, bbox_xyxy, label)
        assigned: Dict[BallId, Tuple[Tuple[float, float], Tuple[float, float, float, float], str]] = {}
        used_det = set()

        # associate existing tracks
        for tid, (tbbox, tts, vx, vy) in list(self._tracks_px.items()):
            if ts - tts > self.cfg.max_age_s:
                del self._tracks_px[tid]
                continue
            dt_pred = max(1e-6, ts - tts)
            pred_bbox = _shift_bbox_xyxy(tbbox, vx * dt_pred, vy * dt_pred)
            best_iou = 0.0
            best_j = -1
            for j, d in enumerate(dets):
                if j in used_det:
                    continue
                v = iou_xyxy(pred_bbox, d.bbox_xyxy)
                if v > best_iou:
                    best_iou = v
                    best_j = j
            if (best_j < 0 or best_iou < self.cfg.iou_match_thres) and self.cfg.center_match_max_dist_px > 0:
                pcc = bbox_center_xy(pred_bbox)
                cand_j, cand_dist = -1, float("inf")
                for j, d in enumerate(dets):
                    if j in used_det:
                        continue
                    dist = l2(pcc, bbox_center_xy(d.bbox_xyxy))
                    if dist < cand_dist and dist <= self.cfg.center_match_max_dist_px:
                        cand_dist = dist
                        cand_j = j
                if cand_j >= 0:
                    best_j, best_iou = cand_j, self.cfg.iou_match_thres
            if best_j >= 0 and best_iou >= self.cfg.iou_match_thres:
                d = dets[best_j]
                used_det.add(best_j)
                dt = max(1e-6, ts - tts)
                ocx, ocy = bbox_center_xy(tbbox)
                ncx, ncy = bbox_center_xy(d.bbox_xyxy)
                nvx = (ncx - ocx) / dt
                nvy = (ncy - ocy) / dt
                self._tracks_px[tid] = (d.bbox_xyxy, ts, nvx, nvy)
                assigned[tid] = (bbox_center_xy(d.bbox_xyxy), d.bbox_xyxy, d.label)

        # create new tracks
        for j, d in enumerate(dets):
            if j in used_det:
                continue
            tid = self._next_id
            self._next_id += 1
            self._tracks_px[tid] = (d.bbox_xyxy, ts, 0.0, 0.0)
            assigned[tid] = (bbox_center_xy(d.bbox_xyxy), d.bbox_xyxy, d.label)

        return assigned
