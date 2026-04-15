#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_phase.sh <phase-number|all>

Examples:
  scripts/run_phase.sh 1
  scripts/run_phase.sh 6
  scripts/run_phase.sh all

Notes:
  - Phase scripts 2/3/4/9 may require runtime inputs (camera/model/class-map).
  - Override paths/settings with env vars (PROJECT_ROOT, MODEL_PATH, etc.).
EOF
}

run_phase() {
  local n="$1"
  local f="$SCRIPT_DIR/phase${n}.sh"
  if [[ ! -x "$f" ]]; then
    echo "Phase script not found or not executable: $f" >&2
    exit 1
  fi
  echo "== Running phase ${n} =="
  "$f"
}

main() {
  if [[ $# -ne 1 ]]; then
    usage
    exit 1
  fi
  local arg="$1"

  case "$arg" in
    1|2|3|4|5|6|7|8|9)
      run_phase "$arg"
      ;;
    all)
      # Run non-interactive phases by default; skip camera/model-dependent phases.
      for n in 1 5 6 7 8; do
        run_phase "$n"
      done
      echo "Completed default all set (1,5,6,7,8)."
      echo "Run phases 2,3,4,9 manually when camera/model are available."
      echo "Phase 3 now supports automated sweep via MODEL_PATH + CLASS_MAP_PATH env vars."
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Invalid phase: $arg" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"

