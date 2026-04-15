#!/usr/bin/env bash
# Create YOLO dataset dirs and billiards-data.yaml with a real absolute `path:` (never a literal $USER string).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root

ROOT="$(pwd)"
DATA_ROOT="$ROOT/data/datasets/billiards"

mkdir -p "$DATA_ROOT/images/train" "$DATA_ROOT/images/val"
mkdir -p "$DATA_ROOT/labels/train" "$DATA_ROOT/labels/val"

/usr/bin/python3 <<PY
from pathlib import Path

root = Path("$ROOT").resolve()
data = root / "data" / "datasets" / "billiards"
yaml_path = data / "billiards-data.yaml"
yaml_path.write_text(
    "\n".join(
        [
            f"path: {data}",
            "train: images/train",
            "val: images/val",
            "names:",
            "  0: ball",
            "  1: person",
            "  2: cue_stick",
            "  3: rack",
            "",
        ]
    ),
    encoding="utf-8",
)
print("Wrote:", yaml_path)
PY
