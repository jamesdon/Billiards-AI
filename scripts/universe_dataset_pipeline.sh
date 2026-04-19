#!/usr/bin/env bash
# Reproducible pipeline: prepare YOLO dirs → download all Universe imports from manifest → merge into billiards/.
#
# Prereq: copy the example manifests once (then edit API key / versions if needed):
#   cp scripts/roboflow_universe_manifest.example.yaml scripts/roboflow_universe_manifest.yaml
#   cp scripts/roboflow_merge_batch.example.yaml scripts/roboflow_merge_batch.yaml
#
# Or use the committed examples directly (no API key in repo — export ROBOFLOW_API_KEY).
#
# Usage:
#   export ROBOFLOW_API_KEY='your-key'
#   bash scripts/universe_dataset_pipeline.sh
#
# Steps only:
#   bash scripts/universe_dataset_pipeline.sh --download-only
#   bash scripts/universe_dataset_pipeline.sh --merge-only
#
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv

MANIFEST="${MANIFEST:-}"
if [[ -z "$MANIFEST" ]]; then
  if [[ -f "$PROJECT_ROOT/scripts/roboflow_universe_manifest.yaml" ]]; then
    MANIFEST="$PROJECT_ROOT/scripts/roboflow_universe_manifest.yaml"
  else
    MANIFEST="$PROJECT_ROOT/scripts/roboflow_universe_manifest.example.yaml"
  fi
fi

MERGE_YAML="${MERGE_YAML:-}"
if [[ -z "$MERGE_YAML" ]]; then
  if [[ -f "$PROJECT_ROOT/scripts/roboflow_merge_batch.yaml" ]]; then
    MERGE_YAML="$PROJECT_ROOT/scripts/roboflow_merge_batch.yaml"
  else
    MERGE_YAML="$PROJECT_ROOT/scripts/roboflow_merge_batch.example.yaml"
  fi
fi

DO_DOWNLOAD=1
DO_MERGE=1
for arg in "$@"; do
  case "$arg" in
    --download-only) DO_MERGE=0 ;;
    --merge-only) DO_DOWNLOAD=0 ;;
    --help|-h)
      echo "Usage: export ROBOFLOW_API_KEY='...' && bash scripts/universe_dataset_pipeline.sh"
      echo "  Uses scripts/roboflow_universe_manifest.yaml if present, else ..._manifest.example.yaml"
      echo "  Uses scripts/roboflow_merge_batch.yaml if present, else ..._merge_batch.example.yaml"
      echo "  Override: MANIFEST=/path MERGE_YAML=/path bash scripts/universe_dataset_pipeline.sh"
      echo "  Flags: --download-only  --merge-only"
      exit 0
      ;;
  esac
done

echo "universe_dataset_pipeline.sh: MANIFEST=$MANIFEST"
echo "universe_dataset_pipeline.sh: MERGE_YAML=$MERGE_YAML"

if [[ "$DO_DOWNLOAD" -eq 1 ]]; then
  if [[ -z "${ROBOFLOW_API_KEY:-}" ]]; then
    echo "ERROR: Set ROBOFLOW_API_KEY for download step." >&2
    exit 1
  fi
  echo "==> 1/3 jetson_prepare_yolo_dataset.sh"
  bash "$PROJECT_ROOT/scripts/jetson_prepare_yolo_dataset.sh"
  echo "==> 2/3 roboflow_universe_pull.py"
  "$VENV_PATH/bin/python3" "$PROJECT_ROOT/scripts/roboflow_universe_pull.py" --manifest "$MANIFEST"
else
  echo "==> Skipping download (--merge-only)"
fi

if [[ "$DO_MERGE" -eq 1 ]]; then
  echo "==> 3/3 merge_yolo_imports_to_billiards.py --batch-yaml"
  "$VENV_PATH/bin/python3" "$PROJECT_ROOT/scripts/merge_yolo_imports_to_billiards.py" --batch-yaml "$MERGE_YAML"
else
  echo "==> Skipping merge (--download-only)"
fi

echo "universe_dataset_pipeline.sh: OK"
echo "Next: bash scripts/jetson_yolo_train.sh"
