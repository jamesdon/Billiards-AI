"""Regression: calib_click must import `edge` when executed as a file (sys.path = scripts/ only by default)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_calib_click_help_does_not_disable_edge_or_diagram() -> None:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "calib_click.py"), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0, (r.stdout, r.stderr)
    err = r.stderr or ""
    assert "package not importable" not in err
    assert "table diagram overlay disabled" not in err
