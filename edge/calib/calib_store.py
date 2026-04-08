from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from core.geometry import Homography
from core.types import PocketLabel


@dataclass(frozen=True)
class PocketDef:
    label: PocketLabel
    center_xy_m: Tuple[float, float]
    radius_m: float


@dataclass
class Calibration:
    H: Homography
    pockets: List[PocketDef]

    @staticmethod
    def load(path: str) -> "Calibration":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        H = Homography(H=np.array(d["H"], dtype=np.float64))
        pockets = [
            PocketDef(
                label=PocketLabel(str(p["label"])),
                center_xy_m=tuple(p["center_xy_m"]),
                radius_m=float(p["radius_m"]),
            )
            for p in d.get("pockets", [])
        ]
        return Calibration(H=H, pockets=pockets)

    def save(self, path: str) -> None:
        d: Dict[str, Any] = {
            "H": self.H.H.tolist(),
            "pockets": [
                {
                    "label": p.label.value,
                    "center_xy_m": [p.center_xy_m[0], p.center_xy_m[1]],
                    "radius_m": p.radius_m,
                }
                for p in self.pockets
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)

