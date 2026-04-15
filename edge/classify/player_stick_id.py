from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List

import cv2
import numpy as np

from core.identity_store import IdentityStore
from core.types import PlayerProfile, StickProfile


def hsv_hist_signature(bgr: np.ndarray, bins: int = 16) -> List[float]:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1]
    mask = s > 40
    if mask.sum() < 10:
        mask = None
    hist = cv2.calcHist([hsv], [0, 1], mask.astype(np.uint8) if mask is not None else None, [bins, bins], [0, 180, 0, 256])
    hist = hist.astype(np.float32).reshape(-1)
    hist /= float(hist.sum() + 1e-6)
    return hist.tolist()


def cosine_sim(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    da = np.array(a, dtype=np.float32)
    db = np.array(b, dtype=np.float32)
    na = float(np.linalg.norm(da) + 1e-9)
    nb = float(np.linalg.norm(db) + 1e-9)
    return float(np.dot(da, db) / (na * nb))


@dataclass
class IdentityMatcherConfig:
    match_thres: float = 0.85
    stick_length_weight: float = 0.20
    stick_length_sigma: float = 0.35


@dataclass
class PlayerStickIdentifier:
    store: IdentityStore
    cfg: IdentityMatcherConfig = field(default_factory=IdentityMatcherConfig)

    def match_or_create_player(self, roi_bgr: np.ndarray, default_name: str = "Player") -> PlayerProfile:
        sig = hsv_hist_signature(roi_bgr)
        best_id, best_sim = None, -1.0
        for pid, prof in self.store.players.items():
            sim = cosine_sim(sig, prof.color_signature)
            if sim > best_sim:
                best_sim = sim
                best_id = pid
        if best_id is not None and best_sim >= self.cfg.match_thres:
            return self.store.players[best_id]
        pid = str(uuid.uuid4())
        prof = PlayerProfile(id=pid, display_name=f"{default_name} {len(self.store.players)+1}", color_signature=sig)
        self.store.upsert_player(prof)
        self.store.save()
        return prof

    def match_or_create_stick(self, roi_bgr: np.ndarray, default_name: str = "Cue") -> StickProfile:
        sig = hsv_hist_signature(roi_bgr)
        best_id, best_sim = None, -1.0
        length_sig = _stick_length_signature_from_roi(roi_bgr)
        for sid, prof in self.store.sticks.items():
            sim = cosine_sim(sig, prof.color_signature)
            sim = _mix_with_length(sim, length_sig, prof.length_signature, self.cfg.stick_length_weight, self.cfg.stick_length_sigma)
            if sim > best_sim:
                best_sim = sim
                best_id = sid
        if best_id is not None and best_sim >= self.cfg.match_thres:
            return self.store.sticks[best_id]
        sid = str(uuid.uuid4())
        prof = StickProfile(
            id=sid,
            display_name=f"{default_name} {len(self.store.sticks)+1}",
            color_signature=sig,
            length_signature=float(length_sig),
        )
        self.store.upsert_stick(prof)
        self.store.save()
        return prof


def _stick_length_signature_from_roi(roi_bgr: np.ndarray) -> float:
    # Proxy: bbox aspect ratio (sticks are long-thin, but detection boxes vary).
    h, w = roi_bgr.shape[:2]
    if h <= 0 or w <= 0:
        return 0.0
    r = max(h, w) / max(1.0, min(h, w))
    # squash to [0,1) for stability
    return float(1.0 - 1.0 / (1.0 + r))


def _mix_with_length(color_sim: float, a: float, b: float, w: float, sigma: float) -> float:
    # Convert length difference to similarity via Gaussian kernel.
    if sigma <= 1e-6:
        return color_sim
    d = float(a - b)
    len_sim = float(np.exp(-(d * d) / (2.0 * sigma * sigma)))
    w = max(0.0, min(1.0, float(w)))
    return (1.0 - w) * float(color_sim) + w * len_sim

