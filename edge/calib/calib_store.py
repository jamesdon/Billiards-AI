from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
    table_length_m: float = 2.84
    table_width_m: float = 1.42
    kitchen_polygon_xy_m: List[Tuple[float, float]] = field(default_factory=list)
    break_area_polygon_xy_m: List[Tuple[float, float]] = field(default_factory=list)
    # Optional 3x3: table meters (x,y) -> projector pixel (homogeneous); for second render target.
    H_projector: Optional[Homography] = None

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
        kitchen: List[Tuple[float, float]] = []
        for pt in d.get("kitchen_polygon_xy_m", []) or []:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                kitchen.append((float(pt[0]), float(pt[1])))
        brk: List[Tuple[float, float]] = []
        for pt in d.get("break_area_polygon_xy_m", []) or []:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                brk.append((float(pt[0]), float(pt[1])))
        hp_raw = d.get("H_projector") or d.get("H_table_to_projector")
        H_projector: Optional[Homography] = None
        if hp_raw is not None:
            H_projector = Homography(H=np.array(hp_raw, dtype=np.float64))
        return Calibration(
            H=H,
            pockets=pockets,
            table_length_m=float(d.get("table_length_m", 2.84)),
            table_width_m=float(d.get("table_width_m", 1.42)),
            kitchen_polygon_xy_m=kitchen,
            break_area_polygon_xy_m=brk,
            H_projector=H_projector,
        )

    def save(self, path: str) -> None:
        d: Dict[str, Any] = {
            "H": self.H.H.tolist(),
            "table_length_m": self.table_length_m,
            "table_width_m": self.table_width_m,
            "kitchen_polygon_xy_m": [[float(x), float(y)] for x, y in self.kitchen_polygon_xy_m],
            "break_area_polygon_xy_m": [[float(x), float(y)] for x, y in self.break_area_polygon_xy_m],
            "pockets": [
                {
                    "label": p.label.value,
                    "center_xy_m": [p.center_xy_m[0], p.center_xy_m[1]],
                    "radius_m": p.radius_m,
                }
                for p in self.pockets
            ],
        }
        if self.H_projector is not None:
            d["H_projector"] = self.H_projector.H.tolist()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
