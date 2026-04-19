from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol

import numpy as np

from core.types import BallObservation


@dataclass(frozen=True)
class DetectorConfig:
    # Match YOLO train/export imgsz (see scripts/jetson_yolo_train.sh default 640).
    input_w: int = 640
    input_h: int = 640
    conf_thres: float = 0.25
    iou_thres: float = 0.45
    max_det: int = 50


class Detector(Protocol):
    def detect(self, frame_bgr: np.ndarray, ts: float) -> List[BallObservation]:
        ...

