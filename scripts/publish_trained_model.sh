#!/usr/bin/env bash
# Stage and commit models/model.onnx (and models/class_map.json if modified) after export.
# Optional: GIT_PUSH=1 to push. Override message: MODEL_COMMIT_MSG="…"
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Not a git repository: $PROJECT_ROOT" >&2
  exit 1
fi

# Avoid mixing unrelated staged work (e.g. calibration deletes) into the model commit.
if ! git diff --cached --quiet 2>/dev/null; then
  echo "publish_trained_model.sh: You already have staged changes. Commit or unstage them first, then re-run." >&2
  echo "Staged paths:" >&2
  git diff --cached --name-only >&2
  exit 1
fi

if [[ ! -f "models/model.onnx" ]]; then
  echo "Missing models/model.onnx — publish only runs after the ONNX exists at that path." >&2
  echo "" >&2
  echo "Create it first, for example:" >&2
  echo "  • Trained here: bash \"$PROJECT_ROOT/scripts/jetson_yolo_export_latest.sh\"" >&2
  echo "  • Full train+export: bash \"$PROJECT_ROOT/scripts/jetson_yolo_train_export_publish.sh\"" >&2
  echo "  • From another machine: copy or scp your exported file to models/model.onnx" >&2
  echo "See docs/MODEL_OPTIMIZATION.md" >&2
  exit 1
fi

# If the tree still ignores the path (stale rules), force-add once.
if git check-ignore -q -- "models/model.onnx" 2>/dev/null; then
  git add -f -- "models/model.onnx"
else
  git add -- "models/model.onnx"
fi

if [[ -f "models/class_map.json" ]] && [[ -n "$(git status --porcelain -- "models/class_map.json" 2>/dev/null || true)" ]]; then
  git add -- "models/class_map.json"
fi

if git diff --cached --quiet; then
  echo "Nothing to commit: models/model.onnx matches HEAD (no staged changes)."
  if [[ "${GIT_PUSH:-0}" == "1" ]]; then
    if git rev-parse --verify '@{u}' >/dev/null 2>&1; then
      _ahead="$(git rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
      if [[ "${_ahead}" -gt 0 ]]; then
        git push
      fi
    else
      echo "GIT_PUSH=1 but no upstream; run: git push -u origin <branch>" >&2
    fi
  fi
  echo "publish_trained_model.sh: OK (no-op)"
  exit 0
fi

_msg="${MODEL_COMMIT_MSG:-chore(models): update detector ONNX (exported weights)}"
git commit -m "$_msg"

if [[ "${GIT_PUSH:-0}" == "1" ]]; then
  git push
fi

echo "publish_trained_model.sh: OK"
