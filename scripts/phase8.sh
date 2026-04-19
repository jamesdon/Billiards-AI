#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

cd_root
activate_venv
PYTHON_BIN="$(python_bin)"

echo "SQLite counts:"
"$PYTHON_BIN" - <<'PY'
import sqlite3, os
db=os.path.join("/Home", os.environ.get("USER",""), "Billiards-AI", "billiards.db")
con=sqlite3.connect(db)
print("events", con.execute("select count(*) from events").fetchone()[0])
print("states", con.execute("select count(*) from states").fetchone()[0])
PY

echo "If Dynamo is configured, run aws dynamodb query manually per docs."

