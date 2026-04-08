from __future__ import annotations

from typing import List

import numpy as np

from core.types import BallObservation


def nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_thres: float, max_det: int) -> List[int]:
    if boxes.size == 0:
        return []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep: List[int] = []
    while order.size > 0 and len(keep) < max_det:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        inds = np.where(iou <= iou_thres)[0]
        order = order[inds + 1]
    return keep


def yolo_like_to_observations(
    preds: np.ndarray,
    conf_thres: float,
    iou_thres: float,
    max_det: int,
) -> List[BallObservation]:
    """
    Convert YOLO-like predictions to BallObservation list.

    Expected format per row: [x1, y1, x2, y2, conf, cls]
    (pixel coords in the original frame space)
    """
    if preds.size == 0:
        return []
    preds = preds[preds[:, 4] >= conf_thres]
    if preds.size == 0:
        return []

    boxes = preds[:, :4].astype(np.float32)
    scores = preds[:, 4].astype(np.float32)
    keep = nms_xyxy(boxes, scores, iou_thres=iou_thres, max_det=max_det)

    out: List[BallObservation] = []
    for i in keep:
        x1, y1, x2, y2, conf, cls = preds[i].tolist()
        out.append(BallObservation(bbox_xyxy=(x1, y1, x2, y2), conf=float(conf), label=str(int(cls))))
    return out

