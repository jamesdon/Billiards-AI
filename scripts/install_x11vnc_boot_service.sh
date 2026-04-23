#!/usr/bin/env bash
# Install x11vnc and enable a systemd service so VNC starts after the graphical stack.
# Run on the Jetson: sudo /home/$USER/Billiards-AI/scripts/install_x11vnc_boot_service.sh
#
# Connect to TCP 5900 (adjust firewall if needed). Set a VNC password strongly recommended:
#   sudo mkdir -p /root/.vnc
#   sudo x11vnc -storepasswd /root/.vnc/passwd
# Then: sudo systemctl edit x11vnc-display0 --full
# and add -rfbauth /root/.vnc/passwd to the ExecStart line (before other flags is fine).

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="${REPO_ROOT}/scripts/systemd/x11vnc-display0.service"
UNIT_DST="/etc/systemd/system/x11vnc-display0.service"

export DEBIAN_FRONTEND=noninteractive
# Do not abort if a third-party list (e.g. GitHub CLI) breaks `apt-get update` — install can still succeed.
set +e
/usr/bin/apt-get -o Acquire::Retries=3 update -qq
upd_rc=$?
set -e
if [[ "$upd_rc" -ne 0 ]]; then
  echo "WARNING: apt-get update exited $upd_rc (often a bad GPG key in /etc/apt/sources.list.d)." >&2
  echo "  Example fix for GitHub CLI: https://github.com/cli/cli/blob/trunk/docs/install_linux.md" >&2
  echo "  Or temporarily: sudo mv /etc/apt/sources.list.d/github-cli.list /etc/apt/sources.list.d/github-cli.list.disabled" >&2
  echo "  Continuing with apt-get install x11vnc …" >&2
fi

/usr/bin/apt-get install -y x11vnc

/usr/bin/install -m 0644 "$UNIT_SRC" "$UNIT_DST"
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable x11vnc-display0.service
/usr/bin/systemctl restart x11vnc-display0.service
/usr/bin/systemctl --no-pager --full status x11vnc-display0.service || true

echo
echo "Enabled: x11vnc-display0.service (port 5900). Check: systemctl is-enabled x11vnc-display0.service"
