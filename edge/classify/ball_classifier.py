from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import numpy as np

from core.types import BallClass, BallTrack, GameType


def _crop(frame_bgr: np.ndarray, bbox: Tuple[float, float, float, float], pad: int = 2) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w - 1, x2 + pad)
    y2 = min(h - 1, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        return frame_bgr[0:1, 0:1]
    return frame_bgr[y1:y2, x1:x2]


def _mean_hsv(roi_bgr: np.ndarray) -> Tuple[float, float, float]:
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    h = float(np.mean(hsv[:, :, 0]))
    s = float(np.mean(hsv[:, :, 1]))
    v = float(np.mean(hsv[:, :, 2]))
    return h, s, v


def _white_ratio(roi_bgr: np.ndarray) -> float:
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(np.float32)
    v = hsv[:, :, 2].astype(np.float32)
    mask = (s < 35) & (v > 170)
    return float(mask.mean())


@dataclass
class BallClassifierConfig:
    ema: float = 0.85


@dataclass
class BallClassifier:
    cfg: BallClassifierConfig = field(default_factory=BallClassifierConfig)

    def update_track(
        self,
        frame_bgr: np.ndarray,
        track: BallTrack,
        game_type: GameType,
        detector_hint: Optional[BallClass] = None,
    ) -> None:
        """
        Update `track.class_probs` in-place using a fast ROI heuristic.

        - `detector_hint` can be used when your model already labels cue/8/9/specific colors.
        """
        if detector_hint is not None and detector_hint != BallClass.UNKNOWN:
            self._ema_set(track, detector_hint, 1.0)
            return

        if track.last_bbox_px is None:
            return
        roi = _crop(frame_bgr, track.last_bbox_px)
        h, s, v = _mean_hsv(roi)
        white = _white_ratio(roi)

        # Cue ball heuristic: low saturation + high value
        if white >= 0.55 and s < 50 and v > 160:
            self._ema_set(track, BallClass.CUE, 1.0)
            return

        # 8 ball heuristic: very dark overall
        if v < 70 and s < 120:
            self._ema_set(track, BallClass.EIGHT, 0.9)
            return

        if game_type in (GameType.EIGHT_BALL, GameType.NINE_BALL, GameType.STRAIGHT_POOL):
            # Solid vs stripe heuristic:
            # stripe balls have a larger "white band" area in the ROI.
            if white >= 0.22:
                self._ema_set(track, BallClass.STRIPE, min(1.0, white * 2.0))
            else:
                self._ema_set(track, BallClass.SOLID, 0.7)
            return

        if game_type == GameType.UK_POOL:
            # red vs yellow by hue (very rough)
            if (h < 15 or h > 165) and s > 80:
                self._ema_set(track, BallClass.UK_RED, 0.9)
            elif 18 <= h <= 40 and s > 80:
                self._ema_set(track, BallClass.UK_YELLOW, 0.9)
            else:
                self._ema_set(track, BallClass.UNKNOWN, 0.4)
            return

        if game_type == GameType.SNOOKER:
            # Snooker colors by hue ranges (very rough baseline)
            # Reds
            if (h < 15 or h > 165) and s > 90:
                self._ema_set(track, BallClass.SNOOKER_RED, 0.8)
            # Yellow/green/brown/blue/pink/black approximations
            elif 18 <= h <= 40 and s > 80:
                self._ema_set(track, BallClass.SNOOKER_YELLOW, 0.8)
            elif 40 < h <= 85 and s > 80:
                self._ema_set(track, BallClass.SNOOKER_GREEN, 0.7)
            elif 10 <= h <= 25 and s < 120 and v < 140:
                self._ema_set(track, BallClass.SNOOKER_BROWN, 0.6)
            elif 90 <= h <= 125 and s > 80:
                self._ema_set(track, BallClass.SNOOKER_BLUE, 0.7)
            elif (h < 15 or h > 165) and s < 90 and v > 120:
                self._ema_set(track, BallClass.SNOOKER_PINK, 0.5)
            elif v < 60:
                self._ema_set(track, BallClass.SNOOKER_BLACK, 0.7)
            else:
                self._ema_set(track, BallClass.UNKNOWN, 0.4)

    def _ema_set(self, track: BallTrack, bc: BallClass, p: float) -> None:
        a = self.cfg.ema
        for k in list(track.class_probs.keys()):
            track.class_probs[k] *= a
        track.class_probs[bc] = track.class_probs.get(bc, 0.0) * a + (1.0 - a) * float(p)
