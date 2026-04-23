#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv

pytest -q "$PROJECT_ROOT/tests/test_rules_8ball.py" "$PROJECT_ROOT/tests/test_rules_9ball.py" "$PROJECT_ROOT/tests/test_end_of_game_straight_pool.py"
echo "Step 6 checks complete."

