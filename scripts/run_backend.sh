#!/usr/bin/env bash
# Run FastAPI backend without relying on .venv/bin/uvicorn (that shim breaks if the repo was
# moved/renamed after venv creation — e.g. shebang still points at "Billiards AI" vs "Billiards-AI").
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/.venv}"
PY="${VENV_PATH}/bin/python3"
if [[ ! -x "$PY" ]]; then
  echo "Missing $PY — create venv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
cd "$PROJECT_ROOT"
export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
HOST="${BACKEND_HOST:-127.0.0.1}"
PORT="${BACKEND_PORT:-8780}"
echo "run_backend.sh: $PY -m uvicorn backend.app:app --host $HOST --port $PORT"
exec "$PY" -m uvicorn backend.app:app --host "$HOST" --port "$PORT" "$@"
