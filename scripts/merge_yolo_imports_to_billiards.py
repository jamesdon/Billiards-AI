#!/usr/bin/env python3
"""
Merge one or more Roboflow YOLOv8 import folders into data/datasets/billiards/{train,val}.

- Prefixes filenames with the import folder name to avoid stem collisions between datasets.
- Remaps label class ids to Billiards-AI ids: 0 ball, 1 person, 2 cue_stick, 3 rack, 4 pockets.

Run after:
  bash scripts/jetson_prepare_yolo_dataset.sh

See also: scripts/roboflow_merge_batch.example.yaml for merging many imports at once.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError as e:  # pragma: no cover
    print("Install PyYAML: python3 -m pip install pyyaml", file=sys.stderr)
    raise SystemExit(1) from e


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_prefix(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_")
    return s[:96] if s else "import"


def _parse_only_source_ids(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def _parse_names_list(raw: object) -> dict[int, str]:
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
        if any(
            x in blob
            for x in (
                "roboflow",
                "collaborate with your team",
                "computer vision platform",
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


def _load_data_yaml(import_root: Path) -> tuple[int | None, dict[int, str]]:
    for name in ("data.yaml", "dataset.yaml"):
        p = import_root / name
        if not p.is_file():
            continue
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None, {}
        nc = data.get("nc")
        if nc is not None:
            try:
                nc = int(nc)
            except (TypeError, ValueError):
                nc = None
        names = _parse_names_list(data.get("names"))
        return nc, names
    return None, {}


def _label_to_billiards_target(name: str | None, nc: int | None) -> int | None:
    """Map Roboflow class name string to Billiards-AI class id, or None to drop."""
    if nc == 1:
        return 0
    if not name:
        return None
    s = str(name).lower().strip()
    if not s or s == "-":
        return None
    if "roboflow" in s or "collaborate" in s or len(s) > 120:
        return None
    if s == "son":
        return 0
    if s == "flag" or re.match(r"^flag\d*$", s):
        return None
    if any(x in s for x in ("bag", "pocket")) or re.match(r"^pocket", s):
        return 4
    if "ball" in s or re.match(r"^ball\d", s) or re.match(r"^ball[-_]", s):
        return 0
    if any(x in s for x in ("solid", "stripe", "eight", "snooker", "billiard")):
        return 0
    if any(x in s for x in ("cue", "stick")):
        return 2
    if any(x in s for x in ("person", "player", "human")):
        return 1
    if any(x in s for x in ("rack", "triangle", "diamond")):
        return 3
    if any(x in s for x in ("table", "felt", "rail", "cushion")):
        return None
    return None


def build_auto_remap(import_root: Path) -> dict[int, int]:
    """Build source id -> target id from data.yaml names + heuristics."""
    nc, names = _load_data_yaml(import_root)
    if nc == 1:
        return {0: 0}
    out: dict[int, int] = {}
    if nc is not None and nc > 0:
        cid_range = range(nc)
    elif names:
        cid_range = range(max(names.keys()) + 1)
    else:
        return {}
    for cid in cid_range:
        tgt = _label_to_billiards_target(names.get(cid), nc)
        if tgt is not None:
            out[cid] = tgt
    return out


def _normalize_remap(raw: dict | None) -> dict[int, int] | None:
    if not raw:
        return None
    out: dict[int, int] = {}
    for k, v in raw.items():
        if v is None:
            continue
        out[int(k)] = int(v)
    return out


def _remap_line(
    line: str,
    id_map: dict[int, int] | None,
    default_class: int,
    only_ids: set[int] | None = None,
) -> str | None:
    parts = line.strip().split()
    if len(parts) != 5:
        return None
    try:
        src = int(float(parts[0]))
    except ValueError:
        return None
    if only_ids is not None and src not in only_ids:
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
    only_ids: set[int] | None,
    dry_run: bool,
) -> tuple[int, int]:
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
                m = _remap_line(line, id_map, default_class, only_ids)
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


def _resolve_imports_base(batch: dict, repo: Path) -> Path:
    raw = batch.get("imports_base", "data/datasets/_imports")
    p = Path(raw)
    return p if p.is_absolute() else (repo / p).resolve()


def _run_batch(
    batch_path: Path,
    dest: Path,
    dry_run: bool,
) -> int:
    batch = yaml.safe_load(batch_path.read_text(encoding="utf-8"))
    if not isinstance(batch, dict):
        print("Batch YAML must be a mapping.", file=sys.stderr)
        raise SystemExit(2)
    repo = _repo_root()
    base = _resolve_imports_base(batch, repo)
    items = batch.get("imports")
    if not isinstance(items, list):
        print("Batch YAML needs `imports:` list.", file=sys.stderr)
        raise SystemExit(2)
    total = 0
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        rel = item.get("path")
        if not rel:
            print(f"imports[{i}]: missing path", file=sys.stderr)
            continue
        imp = Path(rel)
        imp = imp if imp.is_absolute() else (base / imp).resolve()
        if not imp.is_dir():
            print(f"Skip (missing): {imp}", file=sys.stderr)
            continue

        only_ids = None
        if item.get("only_source_ids"):
            only_ids = _parse_only_source_ids(str(item["only_source_ids"]))

        id_map: dict[int, int] | None = None
        if item.get("auto_remap_from_yaml"):
            id_map = build_auto_remap(imp)
            print(f"{imp.name}: auto_remap_from_yaml -> {len(id_map)} source ids mapped")
        elif item.get("remap") is not None:
            id_map = _normalize_remap(item["remap"])
        else:
            print(f"Skip (no remap or auto_remap_from_yaml): {imp}", file=sys.stderr)
            continue

        if not id_map:
            print(f"Skip (empty id map): {imp}", file=sys.stderr)
            continue

        n_img, _ = _merge_one_import(
            imp,
            dest,
            id_map=id_map,
            default_class=0,
            only_ids=only_ids,
            dry_run=dry_run,
        )
        print(f"{imp.name}: images+labels written: {n_img} (dry_run={dry_run})")
        total += n_img
    return total


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Merge Roboflow YOLO imports into data/datasets/billiards train/val."
    )
    ap.add_argument(
        "imports",
        nargs="*",
        default=[],
        type=Path,
        help="Import roots (each with train/images, train/labels, etc.)",
    )
    ap.add_argument(
        "--batch-yaml",
        type=Path,
        default=None,
        help="YAML file with imports list (see roboflow_merge_batch.example.yaml)",
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
        help="YOLO class id when using plain merge without map (default: 0 = ball)",
    )
    ap.add_argument(
        "--map-json",
        type=str,
        default=None,
        help='JSON mapping source class id -> target id',
    )
    ap.add_argument(
        "--only-source-ids",
        type=str,
        default=None,
        help="Comma-separated source class ids to keep, or ranges (e.g. 6-21). Others dropped.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Count only; do not write files",
    )
    args = ap.parse_args()

    dest = args.dest or (_repo_root() / "data" / "datasets" / "billiards")
    dest = dest.resolve()

    if args.batch_yaml is not None:
        batch_path = args.batch_yaml.resolve()
        if not batch_path.is_file():
            print(f"Not found: {batch_path}", file=sys.stderr)
            raise SystemExit(2)
        total = _run_batch(batch_path, dest, args.dry_run)
        print(f"Total pairs merged: {total} -> {dest}")
        if total == 0:
            raise SystemExit(2)
        return

    if not args.imports:
        print("Provide import folder(s) or --batch-yaml.", file=sys.stderr)
        raise SystemExit(2)

    id_map: dict[int, int] | None = None
    if args.map_json:
        raw = json.loads(args.map_json)
        id_map = {int(k): int(v) for k, v in raw.items()}

    only_ids: set[int] | None = None
    if args.only_source_ids:
        only_ids = _parse_only_source_ids(args.only_source_ids)

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
            only_ids=only_ids,
            dry_run=args.dry_run,
        )
        print(f"{imp.name}: images+labels written: {n_img} (dry_run={args.dry_run})")
        total_img += n_img

    print(f"Total pairs merged: {total_img} -> {dest}")
    if total_img == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
