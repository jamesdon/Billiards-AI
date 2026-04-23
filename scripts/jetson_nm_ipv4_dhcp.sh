#!/usr/bin/env bash
# Set a NetworkManager connection back to DHCP (clear static IPv4).
# Default profile is wired — use after moving static IP to Wi-Fi only.
#
#   sudo /home/$USER/Billiards-AI/scripts/jetson_nm_ipv4_dhcp.sh
#   sudo NM_CONNECTION="Some other profile" /home/$USER/Billiards-AI/scripts/jetson_nm_ipv4_dhcp.sh
#
# Jetson onboard Ethernet is usually enP8p1s0 — we pass ifname on connection up so NM
# does not pick the wrong device (e.g. l4tbr0). Override IFNAME=… or SKIP_IFNAME=1 to omit ifname.

set -euo pipefail

NM_CONNECTION="${NM_CONNECTION:-Wired connection 1}"
IFNAME="${IFNAME:-enP8p1s0}"
SKIP_IFNAME="${SKIP_IFNAME:-0}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo so NetworkManager can be reconfigured." >&2
  exit 1
fi

# Do not set ipv4.gateway to "" after clearing addresses — NM errors with:
# "gateway cannot be set if there are no addresses configured".
# Switching to auto is enough for DHCP; optional clears omit gateway.
/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.method auto
/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.ignore-auto-dns no

if [[ "$SKIP_IFNAME" == "1" ]]; then
  /usr/bin/nmcli connection up "$NM_CONNECTION" || true
else
  if /usr/bin/nmcli connection up "$NM_CONNECTION" ifname "$IFNAME"; then
    :
  else
    echo "Note: nmcli connection up failed for ifname=$IFNAME (no cable or wrong IFNAME). Try SKIP_IFNAME=1." >&2
    echo "IPv4 for profile $NM_CONNECTION is still set to automatic (DHCP)." >&2
  fi
fi

echo "Profile: $NM_CONNECTION — IPv4 set to automatic (DHCP)."
