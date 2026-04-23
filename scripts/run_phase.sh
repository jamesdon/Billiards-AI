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
  - `phase2.sh` / `phase4.sh` / `phase9.sh` may require runtime inputs (camera/model/class-map).
  - There is no `phase3.sh`; use `python3 -m edge.main` for detection/tracking (see `docs/3` and the setup guide).
  - Override paths/settings with env vars (PROJECT_ROOT, MODEL_PATH, etc.).
EOF
}

run_phase() {
  local n="$1"
  local f="$SCRIPT_DIR/phase${n}.sh"
  if [[ ! -x "$f" ]]; then
    echo "Script not found or not executable: $f" >&2
    exit 1
  fi
  echo "== Running step ${n} (phase${n}.sh) =="
  "$f"
}

main() {
  if [[ $# -ne 1 ]]; then
    usage
    exit 1
  fi
  local arg="$1"

  case "$arg" in
    1|2|4|5|6|7|8|9)
      run_phase "$arg"
      ;;
    all)
      # Run non-interactive steps by default; skip camera/model-dependent steps.
      for n in 1 5 6 7 8; do
        run_phase "$n"
      done
      echo "Completed default all set (1,5,6,7,8)."
      echo "Run steps 2,4,9 (phase2.sh, phase4.sh, phase9.sh) manually when camera/model are available."
      echo "Detection/tracking: run edge.main (see docs/3) — not a numbered phase script."
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "Invalid step number: $arg" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"

