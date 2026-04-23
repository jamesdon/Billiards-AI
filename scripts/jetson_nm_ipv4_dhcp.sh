#!/usr/bin/env bash
# Set a NetworkManager connection back to DHCP (clear static IPv4).
# Default profile is wired — use after moving static IP to Wi-Fi only.
#
#   sudo /home/$USER/Billiards-AI/scripts/jetson_nm_ipv4_dhcp.sh
#   sudo NM_CONNECTION="Some other profile" /home/$USER/Billiards-AI/scripts/jetson_nm_ipv4_dhcp.sh

set -euo pipefail

NM_CONNECTION="${NM_CONNECTION:-Wired connection 1}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo so NetworkManager can be reconfigured." >&2
  exit 1
fi

/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.method auto
/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.addresses ""
/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.gateway ""
/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.dns ""
/usr/bin/nmcli connection modify "$NM_CONNECTION" ipv4.ignore-auto-dns no

/usr/bin/nmcli connection up "$NM_CONNECTION" || true

echo "Profile: $NM_CONNECTION — IPv4 set to automatic (DHCP)."
