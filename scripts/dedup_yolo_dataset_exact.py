#!/usr/bin/env python3
"""
Exact duplicate detection for a YOLO dataset layout (images + labels per split).

Duplicates are defined by SHA-256 of raw file bytes (same image file copied under
different names counts as one group).

Default mode is dry-run: print groups and suggested removals, delete nothing.

Example:
  python3 scripts/dedup_yolo_dataset_exact.py
  python3 scripts/dedup_yolo_dataset_exact.py --dataset-root /path/to/billiards
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

# Match training script image extensions
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _collect_images(images_dir: Path) -> list[Path]:
    if not images_dir.is_dir():
        return []
    out: list[Path] = []
    for p in images_dir.iterdir():
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES:
            out.append(p)
    return sorted(out)


def _label_for_image(dataset_root: Path, split: str, image_path: Path) -> Path:
    return dataset_root / "labels" / split / f"{image_path.stem}.txt"


def _analyze_split(
    dataset_root: Path, split: str
) -> tuple[dict[str, list[Path]], list[tuple[str, Path, Path]]]:
    """
    Returns:
      hash -> list of image paths (only groups with len > 1 are duplicates)
      warnings: (message, path_a, path_b) for same-hash but different labels
    """
    images_dir = dataset_root / "images" / split
    paths = _collect_images(images_dir)
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for p in paths:
        try:
            digest = _sha256_file(p)
        except OSError as e:
            print(f"ERROR: cannot read {p}: {e}", file=sys.stderr)
            continue
        by_hash[digest].append(p)

    dup_groups = {h: ps for h, ps in by_hash.items() if len(ps) > 1}
    warnings: list[tuple[str, Path, Path]] = []
    for h, ps in dup_groups.items():
        labels = [_label_for_image(dataset_root, split, x) for x in ps]
        contents: list[bytes | None] = []
        for lp in labels:
            if lp.is_file():
                contents.append(lp.read_bytes())
            else:
                contents.append(None)
        unique_non_null = {c for c in contents if c is not None}
        if len(unique_non_null) > 1:
            # find two differing label files for message
            a, b = None, None
            for i, c in enumerate(contents):
                if c is None:
                    continue
                for j, d in enumerate(contents):
                    if j <= i or d is None:
                        continue
                    if c != d:
                        a, b = ps[i], ps[j]
                        break
                if a is not None:
                    break
            if a is not None and b is not None:
                warnings.append(("same image hash but different label files", a, b))

    return dup_groups, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="YOLO dataset exact-duplicate report (dry-run by default).")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=_repo_root() / "data" / "datasets" / "billiards",
        help="Dataset root containing images/{train,val} and labels/{train,val}",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Remove duplicate images (keeps lexicographically first path per hash) and orphan labels. "
        "Default is dry-run only.",
    )
    args = parser.parse_args()
    root: Path = args.dataset_root.resolve()

    if not root.is_dir():
        print(f"ERROR: dataset root does not exist: {root}", file=sys.stderr)
        raise SystemExit(1)

    if args.apply:
        print("ERROR: --apply is not enabled yet; run without --apply for a dry-run report.", file=sys.stderr)
        raise SystemExit(2)

    splits = ["train", "val"]
    total_images = 0
    total_dup_files = 0
    total_groups = 0

    print(f"dedup_yolo_dataset_exact.py: dataset_root={root}")
    print("Mode: dry-run (no files deleted)")
    print()

    for split in splits:
        dup_groups, warnings = _analyze_split(root, split)
        imgs = _collect_images(root / "images" / split)
        total_images += len(imgs)
        for w, pa, pb in warnings:
            print(f"WARNING [{split}]: {w}")
            print(f"    {pa}")
            print(f"    {pb}")
            print()

        if not dup_groups:
            print(f"[{split}] No exact duplicate image hashes (multipart groups).")
            print()
            continue

        print(f"[{split}] Duplicate groups (by SHA-256): {len(dup_groups)}")
        for h in sorted(dup_groups.keys()):
            paths = sorted(dup_groups[h])
            keep = paths[0]
            remove = paths[1:]
            total_groups += 1
            total_dup_files += len(remove)
            print(f"  hash {h[:16]}… ({len(paths)} files)  KEEP: {keep.name}")
            for r in remove:
                print(f"      remove: {r.name}")
                lt = _label_for_image(root, split, r)
                if lt.is_file():
                    print(f"              label: {lt.name} (orphan if image removed)")
                elif any(_label_for_image(root, split, k).is_file() for k in paths):
                    print(f"              label: (none for this name)")
            print()

    # Cross-split leakage: same content in train and val (include singletons)
    def all_hash_set(split: str) -> dict[str, list[Path]]:
        images_dir = root / "images" / split
        out: dict[str, list[Path]] = defaultdict(list)
        for p in _collect_images(images_dir):
            try:
                out[_sha256_file(p)].append(p)
            except OSError:
                continue
        return dict(out)

    full_train = all_hash_set("train")
    full_val = all_hash_set("val")
    common = set(full_train.keys()) & set(full_val.keys())
    if common:
        print("[train vs val] Same image bytes appear in BOTH splits (metric leakage risk):")
        for h in sorted(common):
            print(f"  hash {h[:16]}…")
            for p in sorted(full_train[h]):
                print(f"    train: {p.name}")
            for p in sorted(full_val[h]):
                print(f"    val:   {p.name}")
        print()
    else:
        print("[train vs val] No overlapping image hashes between splits.")
        print()

    print("Summary")
    print(f"  Images scanned (train+val): {total_images}")
    print(f"  Duplicate groups:           {total_groups}")
    print(f"  Redundant files (would remove in --apply): {total_dup_files}")
    print()
    print("Next: review warnings; when satisfied, ask to enable --apply or delete manually.")


if __name__ == "__main__":
    main()
