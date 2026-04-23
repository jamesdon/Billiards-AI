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

require_file "models/model.onnx"

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
  echo "publish_trained_model.sh: OK (no-op)"
  exit 0
fi

_msg="${MODEL_COMMIT_MSG:-chore(models): update detector ONNX (exported weights)}"
git commit -m "$_msg"

if [[ "${GIT_PUSH:-0}" == "1" ]]; then
  git push
fi

echo "publish_trained_model.sh: OK"
