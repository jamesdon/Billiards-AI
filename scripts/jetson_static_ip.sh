#!/usr/bin/env bash
# Apply static IPv4 via NetworkManager (Jetson / Ubuntu images using NM, no netplan).
# Run on the device: sudo /home/$USER/Billiards-AI/scripts/jetson_static_ip.sh
#
# Override with env vars, e.g. wired profile:
#   sudo NM_CONNECTION="Wired connection 1" STATIC_IPV4=192.168.1.102 /home/$USER/Billiards-AI/scripts/jetson_static_ip.sh
# To revert a profile to DHCP (e.g. wired after using Wi-Fi static): see jetson_nm_ipv4_dhcp.sh

set -euo pipefail

NM_CONNECTION="${NM_CONNECTION:-Ether 2}"
STATIC_IPV4="${STATIC_IPV4:-192.168.1.102}"
PREFIX="${PREFIX:-24}"
GATEWAY="${GATEWAY:-192.168.1.1}"
DNS_SERVERS="${DNS_SERVERS:-192.168.1.1}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo so NetworkManager can be reconfigured." >&2
  exit 1
fi

/usr/bin/nmcli connection modify "$NM_CONNECTION" \
  ipv4.method manual \
  ipv4.addresses "${STATIC_IPV4}/${PREFIX}" \
  ipv4.gateway "$GATEWAY" \
  ipv4.dns "$DNS_SERVERS"

/usr/bin/nmcli connection up "$NM_CONNECTION"

echo "Profile: $NM_CONNECTION"
echo "IPv4:    ${STATIC_IPV4}/${PREFIX}  gateway ${GATEWAY}  DNS ${DNS_SERVERS}"
