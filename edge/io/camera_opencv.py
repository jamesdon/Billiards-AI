from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterator, Optional, Tuple

try:
    import cv2
except Exception as exc:  # pragma: no cover - import-time environment issue
    raise RuntimeError(
        "Failed to import OpenCV (cv2). On Jetson this is commonly caused by a NumPy/OpenCV ABI mismatch.\n"
        "Use distro OpenCV with a NumPy<2 runtime in your venv:\n"
        "  python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless\n"
        "  python -m pip install \"numpy<2\"\n"
        "  sudo /usr/bin/apt-get install -y python3-opencv python3-gst-1.0 gstreamer1.0-tools"
    ) from exc
import numpy as np


def opencv_gstreamer_enabled() -> bool:
    try:
        info = cv2.getBuildInformation()
    except Exception:
        return False
    for line in info.splitlines():
        if "GStreamer" in line:
            return "YES" in line.upper()
    return False


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
        if self.use_gstreamer and not opencv_gstreamer_enabled():
            raise RuntimeError(
                "OpenCV was built without GStreamer support, so Jetson CSI sources cannot be opened. "
                "Use a GStreamer-enabled OpenCV build on Jetson (for example the distro python3-opencv package), "
                "and avoid venv-only opencv-python wheels that lack GStreamer."
            )

        cap = None
        attempts = 3 if self.use_gstreamer else 1
        for attempt in range(attempts):
            if self.use_gstreamer:
                cap = cv2.VideoCapture(self.source, cv2.CAP_GSTREAMER)
            else:
                cap = cv2.VideoCapture(self.source)
            if self.width is not None:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.width))
            if self.height is not None:
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.height))
            if cap.isOpened():
                break
            cap.release()
            cap = None
            if attempt < attempts - 1:
                time.sleep(0.5)

        if cap is None:
            raise RuntimeError(f"Failed to open camera source={self.source!r}")

        yielded = False
        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                yielded = True
                ts = cv2.getTickCount() / cv2.getTickFrequency()
                yield ts, frame
        finally:
            cap.release()

        if not yielded:
            raise RuntimeError(
                "Camera capture reported isOpened() but returned no frames (pipeline may have failed). "
                "On Jetson CSI, check nvarguscamerasrc / Argus errors, sensor-id, flip-method, and that "
                "no other process is using the camera."
            )

