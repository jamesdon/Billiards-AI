#!/usr/bin/env bash
# Put detector weights at models/model.onnx: normalize wrong locations, then latest local export, then remind git pull.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
/usr/bin/mkdir -p "$PROJECT_ROOT/models"

_dest="$PROJECT_ROOT/models/model.onnx"

_sz="$(/usr/bin/wc -c <"$_dest" 2>/dev/null | tr -d '[:space:]' || echo 0)"
if [[ -f "$_dest" ]] && [[ "${_sz:-0}" -gt 1000 ]]; then
  echo "ensure_models_model_onnx.sh: OK (already: $_dest)"
  exit 0
fi

# Wrong-but-common locations → canonical path
for _cand in "$PROJECT_ROOT/model.onnx" "$PROJECT_ROOT/best.onnx" "$PROJECT_ROOT/models/best.onnx"; do
  if [[ -f "$_cand" ]]; then
    echo "Moving $_cand -> $_dest"
    /usr/bin/mv "$_cand" "$_dest"
    echo "ensure_models_model_onnx.sh: OK"
    exit 0
  fi
done

_latest_onnx="$(/usr/bin/ls -t "$PROJECT_ROOT"/runs/detect/*/weights/best.onnx 2>/dev/null | /usr/bin/head -1 || true)"
if [[ -n "$_latest_onnx" && -f "$_latest_onnx" ]]; then
  echo "Copying $_latest_onnx -> $_dest"
  /usr/bin/cp -f "$_latest_onnx" "$_dest"
  echo "ensure_models_model_onnx.sh: OK"
  exit 0
fi

echo "ensure_models_model_onnx.sh: No local model.onnx and no runs/.../best.onnx to copy." >&2
echo "Run from repo root:" >&2
echo "  git pull origin main" >&2
echo "If the team committed models/model.onnx, that pull will create it. Otherwise train/export on a machine with data." >&2
exit 1
