#!/usr/bin/env python3
"""
Download Roboflow Universe dataset versions listed in a YAML manifest.

Manifest format (see scripts/roboflow_universe_manifest.example.yaml):
  imports:
    - workspace: pool-table
      project: pool-v2
      version: 1
      dirname: pool-table_pool-v2

Environment:
  ROBOFLOW_API_KEY  required (do not commit the key)

Usage:
  export ROBOFLOW_API_KEY='...'
  python3 scripts/roboflow_universe_pull.py --manifest scripts/roboflow_universe_manifest.yaml
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:  # pragma: no cover
    print("Install PyYAML: python3 -m pip install pyyaml", file=sys.stderr)
    raise SystemExit(1) from e


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch-download Roboflow Universe YOLOv8 zips.")
    ap.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="YAML file with an `imports:` list (see roboflow_universe_manifest.example.yaml)",
    )
    ap.add_argument(
        "--out-base",
        type=Path,
        default=None,
        help="Parent directory for downloads (default: <repo>/data/datasets/_imports)",
    )
    args = ap.parse_args()

    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not key:
        print("Set ROBOFLOW_API_KEY in the environment.", file=sys.stderr)
        raise SystemExit(2)

    manifest_path = args.manifest.resolve()
    if not manifest_path.is_file():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        raise SystemExit(2)

    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    imports = raw.get("imports") if isinstance(raw, dict) else None
    if not isinstance(imports, list) or not imports:
        print("Manifest must contain a non-empty `imports:` list.", file=sys.stderr)
        raise SystemExit(2)

    out_base = args.out_base or (_repo_root() / "data" / "datasets" / "_imports")
    out_base.mkdir(parents=True, exist_ok=True)

    try:
        from roboflow import Roboflow
    except ImportError as e:  # pragma: no cover
        print("Install roboflow: python3 -m pip install roboflow", file=sys.stderr)
        raise SystemExit(1) from e

    rf = Roboflow(api_key=key)

    for i, item in enumerate(imports):
        if not isinstance(item, dict):
            print(f"imports[{i}] must be a mapping, got {type(item)}", file=sys.stderr)
            raise SystemExit(2)
        ws = str(item.get("workspace", "")).strip()
        proj = str(item.get("project", "")).strip()
        ver = item.get("version")
        dirname = str(item.get("dirname", "")).strip()
        if not (ws and proj and dirname):
            print(f"imports[{i}] needs workspace, project, dirname", file=sys.stderr)
            raise SystemExit(2)
        try:
            ver = int(ver)
        except (TypeError, ValueError):
            print(f"imports[{i}] version must be an integer, got {ver!r}", file=sys.stderr)
            raise SystemExit(2)

        dest = out_base / dirname
        print(f"Downloading {ws}/{proj} v{ver} -> {dest}")
        p = rf.workspace(ws).project(proj)
        p.version(ver).download("yolov8", location=str(dest))
        print(f"  OK: {dest}\n")

    print("Done. Run: python3 scripts/yolo_import_class_report.py --imports-dir", out_base)


if __name__ == "__main__":
    main()
