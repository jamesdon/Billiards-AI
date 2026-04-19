#!/usr/bin/env python3
"""
Merge one or more Roboflow YOLOv8 import folders into data/datasets/billiards/{train,val}.

- Prefixes filenames with the import folder name to avoid stem collisions between datasets.
- Remaps every label line to a target class id (default 0 = ball) unless --map is given.

Run after:
  bash scripts/jetson_prepare_yolo_dataset.sh

Usage (ball-only merge, all sources -> class 0):
  python3 scripts/merge_yolo_imports_to_billiards.py \\
    /path/to/Billiards-AI/data/datasets/_imports/jdq_table2-kfsub \\
    /path/to/Billiards-AI/data/datasets/_imports/pool-table_pool-v2

  python3 scripts/merge_yolo_imports_to_billiards.py \\
    --default-class 0 \\
    data/datasets/_imports/jdq_table2-kfsub

Per-source class map (JSON object: source_id -> target_id), e.g. map all to ball:
  python3 scripts/merge_yolo_imports_to_billiards.py --map-json '{"0":0,"1":0,"2":0,"3":0}' IMPORT_DIR
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_prefix(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_")
    return s[:96] if s else "import"


def _remap_line(
    line: str,
    id_map: dict[int, int] | None,
    default_class: int,
) -> str | None:
    parts = line.strip().split()
    if len(parts) != 5:
        return None
    try:
        src = int(float(parts[0]))
    except ValueError:
        return None
    cx, cy, w, h = parts[1:5]
    if id_map is not None:
        if src not in id_map:
            return None
        tid = id_map[src]
    else:
        tid = default_class
    return f"{tid} {cx} {cy} {w} {h}"


def _merge_one_import(
    import_root: Path,
    dest_root: Path,
    *,
    id_map: dict[int, int] | None,
    default_class: int,
    dry_run: bool,
) -> tuple[int, int]:
    """Returns (images_copied, labels_written)."""
    prefix = _safe_prefix(import_root.name)
    n_img = 0
    n_lbl = 0
    for rob_split, bill_split in (("train", "train"), ("valid", "val"), ("val", "val")):
        img_dir = import_root / rob_split / "images"
        lbl_dir = import_root / rob_split / "labels"
        if not img_dir.is_dir() or not lbl_dir.is_dir():
            continue
        out_img = dest_root / "images" / bill_split
        out_lbl = dest_root / "labels" / bill_split
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                continue
            stem = img.stem
            src_txt = lbl_dir / f"{stem}.txt"
            if not src_txt.is_file():
                continue
            new_name = f"{prefix}__{stem}{img.suffix.lower()}"
            new_stem = f"{prefix}__{stem}"
            dst_img = out_img / new_name
            dst_txt = out_lbl / f"{new_stem}.txt"
            lines_out: list[str] = []
            for line in src_txt.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _remap_line(line, id_map, default_class)
                if m:
                    lines_out.append(m)
            if not lines_out:
                continue
            text = "\n".join(lines_out) + "\n"
            if dry_run:
                n_img += 1
                n_lbl += 1
                continue
            out_img.mkdir(parents=True, exist_ok=True)
            out_lbl.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dst_img)
            dst_txt.write_text(text, encoding="utf-8")
            n_img += 1
            n_lbl += 1
    return n_img, n_lbl


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Merge Roboflow YOLO imports into data/datasets/billiards train/val."
    )
    ap.add_argument(
        "imports",
        nargs="+",
        type=Path,
        help="Import roots (each with train/images, train/labels, etc.)",
    )
    ap.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Billiards dataset root (default: <repo>/data/datasets/billiards)",
    )
    ap.add_argument(
        "--default-class",
        type=int,
        default=0,
        help="YOLO class id to write when --map-json is omitted (default: 0 = ball)",
    )
    ap.add_argument(
        "--map-json",
        type=str,
        default=None,
        help='Optional JSON object mapping source class id -> target id, e.g. \'{"0":0,"1":0}\'',
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Count only; do not write files",
    )
    args = ap.parse_args()

    dest = args.dest or (_repo_root() / "data" / "datasets" / "billiards")
    dest = dest.resolve()

    id_map: dict[int, int] | None = None
    if args.map_json:
        raw = json.loads(args.map_json)
        id_map = {int(k): int(v) for k, v in raw.items()}

    total_img = 0
    for imp in args.imports:
        imp = imp.resolve()
        if not imp.is_dir():
            print(f"Skip (not a directory): {imp}", file=sys.stderr)
            continue
        n_img, n_lbl = _merge_one_import(
            imp,
            dest,
            id_map=id_map,
            default_class=args.default_class,
            dry_run=args.dry_run,
        )
        print(f"{imp.name}: images+labels written: {n_img} (dry_run={args.dry_run})")
        total_img += n_img

    print(f"Total pairs merged: {total_img} -> {dest}")
    if total_img == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
