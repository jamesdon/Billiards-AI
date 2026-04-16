from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from core.geometry import Homography
from edge.calib.calib_store import Calibration, PocketDef
from core.types import PocketLabel


def test_calibration_roundtrip_optional_H_projector():
    H = np.eye(3, dtype=np.float64)
    Hp = np.array([[100.0, 0.0, 10.0], [0.0, 100.0, 20.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    pockets = [
        PocketDef(label=PocketLabel.TOP_LEFT_CORNER, center_xy_m=(0.1, 0.2), radius_m=0.05),
    ]
    c = Calibration(
        H=Homography(H=H),
        pockets=pockets,
        H_projector=Homography(H=Hp),
    )
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cal.json"
        c.save(str(p))
        c2 = Calibration.load(str(p))
    assert c2.H_projector is not None
    np.testing.assert_array_almost_equal(c2.H_projector.H, Hp)


def test_calibration_H_table_to_projector_alias_loads():
    import json

    d = {
        "H": np.eye(3).tolist(),
        "pockets": [],
        "H_table_to_projector": [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]],
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        c = Calibration.load(str(p))
    assert c.H_projector is not None
    assert float(c.H_projector.H[0, 0]) == 2.0
