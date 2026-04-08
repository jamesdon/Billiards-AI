from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

import cv2
import numpy as np


def jetson_csi_gstreamer_pipeline(
    sensor_id: int = 0,
    capture_width: int = 1280,
    capture_height: int = 720,
    display_width: int = 1280,
    display_height: int = 720,
    framerate: int = 30,
    flip_method: int = 0,
) -> str:
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width=(int){capture_width}, height=(int){capture_height}, "
        f"format=(string)NV12, framerate=(fraction){framerate}/1 ! "
        f"nvvidconv flip-method={flip_method} ! "
        f"video/x-raw, width=(int){display_width}, height=(int){display_height}, format=(string)BGRx ! "
        f"videoconvert ! video/x-raw, format=(string)BGR ! appsink drop=true max-buffers=1"
    )


@dataclass
class OpenCVCamera:
    source: int | str = 0
    width: Optional[int] = None
    height: Optional[int] = None
    use_gstreamer: bool = False

    def frames(self) -> Iterator[Tuple[float, np.ndarray]]:
        if self.use_gstreamer:
            cap = cv2.VideoCapture(self.source, cv2.CAP_GSTREAMER)
        else:
            cap = cv2.VideoCapture(self.source)
        if self.width is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
        if self.height is not None:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))

        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera source={self.source!r}")

        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                ts = cv2.getTickCount() / cv2.getTickFrequency()
                yield ts, frame
        finally:
            cap.release()

