#!/usr/bin/env python3
"""
Summarize YOLO label class ids for one or more import trees (Roboflow zip layout or similar).

Prints:
  - nc / names from data.yaml when parseable
  - Per-class-id box counts across train/valid/test labels
  - Heuristic mapping hints -> Billiards-AI ids (0 ball, 1 person, 2 cue_stick, 3 rack, 4 pockets) or DROP

Usage:
  python3 scripts/yolo_import_class_report.py \\
    /Users/you/Billiards-AI/data/datasets/_imports/pool-table_pool-v2 \\
    /Users/you/Billiards-AI/data/datasets/_imports/other-dataset
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import yaml
except ImportError as e:  # pragma: no cover
    print("Install PyYAML: python3 -m pip install pyyaml", file=sys.stderr)
    raise SystemExit(1) from e


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _iter_label_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("train", "valid", "val", "test"):
        d = root / sub / "labels"
        if d.is_dir():
            out.extend(sorted(d.glob("*.txt")))
    if not out:
        out.extend(sorted(root.rglob("labels/*.txt")))
    return out


def _parse_names(raw: object, nc: int | None) -> dict[int, str]:
    """Build id -> label string for display."""
    names: dict[int, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                names[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        return names
    if isinstance(raw, list):
        blob = " ".join(str(v) for v in raw if v is not None).lower()
        # Roboflow sometimes writes junk / marketing lines into `names:`; do not align to class ids.
        if any(
            x in blob
            for x in (
                "roboflow",
                "collaborate with your team",
                "computer vision platform",
                "universe.roboflow.com",
            )
        ):
            return {}
        for i, v in enumerate(raw):
            if v is None:
                continue
            s = str(v).strip()
            if not s or s == "-":
                continue
            if len(s) > 80 or "http" in s.lower():
                continue
            names[i] = s
        return names
    return names


def _load_data_yaml(root: Path) -> tuple[int | None, dict[int, str], str | None]:
    for name in ("data.yaml", "dataset.yaml"):
        p = root / name
        if not p.is_file():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover
            return None, {}, f"yaml error: {exc}"
        if not isinstance(data, dict):
            return None, {}, "yaml root is not a dict"
        nc = data.get("nc")
        if nc is not None:
            try:
                nc = int(nc)
            except (TypeError, ValueError):
                nc = None
        names = _parse_names(data.get("names"), nc)
        return nc, names, None
    return None, {}, "no data.yaml / dataset.yaml"


def _count_classes(label_files: list[Path]) -> Counter[int]:
    c: Counter[int] = Counter()
    for lf in label_files:
        try:
            text = lf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                cid = int(float(parts[0]))
            except ValueError:
                continue
            c[cid] += 1
    return c


def _readme_title(root: Path) -> str | None:
    p = root / "README.roboflow.txt"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s and not s.startswith("=") and "roboflow.com" not in s.lower():
            return s[:200]
    return None


def _yaml_class_label_suspicious(names: dict[int, str], nc: int | None) -> bool:
    """True when data.yaml's human-readable class name looks truncated or wrong."""
    if nc != 1 or not names or 0 not in names:
        return False
    s = str(names[0]).strip().lower()
    if len(s) <= 4 and s not in ("ball", "balls", "rack", "cue", "nine", "eight"):
        return True
    if _suggest_canonical(str(names[0])) == "MANUAL_REVIEW" and len(s) < 12:
        return True
    return False


def _suggest_canonical(label: str) -> str:
    s = label.lower().strip()
    if not s:
        return "MANUAL_REVIEW"
    if any(
        x in s
        for x in (
            "pocket",
            "hole",
            "rail",
            "felt",
            "table",
            "pockets",
            "cushion",
            "pocket ",
        )
    ) or re.match(r"^bag\d*$", s):
        return "4 pockets (class id 4; not 'bags' at runtime)"
    if s == "flag" or re.match(r"^flag\d*$", s):
        return "DROP"
    if any(x in s for x in ("rack", "triangle", "diamond", "frame")):
        return "3 rack"
    if any(x in s for x in ("person", "player", "human", "hand", "arm", "body")):
        return "1 person"
    if any(x in s for x in ("cue", "stick", "pool cue")):
        return "2 cue_stick"
    if s == "rod" or re.match(r"^rod\d*$", s):
        return "2 cue_stick (pool cue as 'rod' in some datasets)"
    if any(
        x in s
        for x in (
            "ball",
            "stripe",
            "solid",
            "eight",
            "9-ball",
            "snooker",
            "billiard",
        )
    ) or re.match(r"^ball\d*$", s) or re.match(r"^ball[-_]", s):
        return "0 ball"
    return "MANUAL_REVIEW"


def _report_one(root: Path) -> None:
    root = root.resolve()
    print("=" * 72)
    print(f"Import: {root}")
    print("=" * 72)
    if not root.is_dir():
        print(f"  ERROR: not a directory\n")
        return

    nc, names, yerr = _load_data_yaml(root)
    label_files = _iter_label_files(root)
    counts = _count_classes(label_files)
    ids_seen = sorted(counts.keys())

    if yerr:
        print(f"  data.yaml: ({yerr})")
    else:
        print(f"  data.yaml nc: {nc}")
        if names:
            print("  names (parsed, may be incomplete if export is broken):")
            for i in sorted(names):
                print(f"    {i}: {names[i]!r}")
        else:
            print("  names: (none parseable — use Universe class list or inspect images)")

    readme_title = _readme_title(root)
    if readme_title:
        print(f"  README.roboflow.txt (title): {readme_title!r}")
    if names and _yaml_class_label_suspicious(names, nc):
        print(
            "  WARNING: `names` in data.yaml does not look like a real class label (truncated export"
        )
        print(
            "            or bad metadata on Universe). Trust README + sample images, not that string."
        )

    print(f"  label files scanned: {len(label_files)}")
    if not ids_seen:
        print("  No YOLO boxes found (no labels under train|valid|val|test?).\n")
        return

    print("  class_id -> box_count:")
    for cid in ids_seen:
        n = names.get(cid, "?")
        print(f"    {cid:>3}  {counts[cid]:>6}  {n!r}")

    print("  Heuristic -> Billiards-AI (verify before merging):")
    single_ball = nc == 1 and ids_seen == [0]
    if single_ball:
        print("    source 0 -> 0 ball (single-class YOLO head: entire dataset is one detection class)")
        if names.get(0) and names[0] != "?":
            print(f"      (yaml calls it {names[0]!r} — often wrong; README/images define intent)")
    else:
        for cid in ids_seen:
            label = names.get(cid, "")
            hint = (
                _suggest_canonical(label) if label and label != "?" else "MANUAL_REVIEW (no label string)"
            )
            print(f"    source {cid} -> {hint}")
    if not names and ids_seen and max(ids_seen) < 16:
        print(
            "  NOTE: Unreliable or missing `names:` in data.yaml. Confirm semantics on the Universe"
        )
        print(
            "        dataset page (class list) or by opening image+label pairs per id. Until then,"
        )
        print(
            "        a conservative merge for unknown small id sets is: map every id -> 0 (ball).\n"
        )
    else:
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description="YOLO import class summary + mapping hints.")
    ap.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="Import roots (each should contain data.yaml and train/labels, etc.)",
    )
    ap.add_argument(
        "--imports-dir",
        type=Path,
        default=None,
        help=f"Report on every subdir under this path (default: {_repo_root() / 'data' / 'datasets' / '_imports'})",
    )
    args = ap.parse_args()
    roots: list[Path] = [Path(p) for p in args.paths]
    if args.imports_dir is not None:
        base = args.imports_dir.resolve()
        if base.is_dir():
            roots.extend(sorted(p for p in base.iterdir() if p.is_dir()))
    if not roots:
        default_imports = _repo_root() / "data" / "datasets" / "_imports"
        if default_imports.is_dir():
            roots = sorted(p for p in default_imports.iterdir() if p.is_dir())
    if not roots:
        print("No paths given and no subdirs under data/datasets/_imports.", file=sys.stderr)
        raise SystemExit(2)
    for r in roots:
        _report_one(r)


if __name__ == "__main__":
    main()
