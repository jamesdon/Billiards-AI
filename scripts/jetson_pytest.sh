#!/usr/bin/env bash
# Block 5: pytest
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"
"$PYTHON_BIN" -m pytest "$PROJECT_ROOT/tests" -q --tb=short
echo "jetson_pytest.sh: OK"
