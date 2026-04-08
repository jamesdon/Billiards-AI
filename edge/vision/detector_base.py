from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol

import numpy as np

from core.types import BallObservation


@dataclass(frozen=True)
class DetectorConfig:
    input_w: int = 416
    input_h: int = 416
    conf_thres: float = 0.25
    iou_thres: float = 0.45
    max_det: int = 50


class Detector(Protocol):
    def detect(self, frame_bgr: np.ndarray, ts: float) -> List[BallObservation]:
        ...

