"""
Canonical on-disk path for player/stick profiles.

Both FastAPI (`GET /profiles`, Score Keeper) and `edge.main` use this file:
`<repository root>/identities.json`
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    """Return the Billiards-AI repository root (directory containing `core/`, `edge/`, `backend/`)."""
    return _REPO_ROOT


def identities_json_path() -> Path:
    return _REPO_ROOT / "identities.json"


def identities_json_str() -> str:
    return str(identities_json_path())
