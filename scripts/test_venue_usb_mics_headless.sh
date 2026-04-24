#!/usr/bin/env bash
# Headless test for dual USB TRS adapters (e.g. Movo VXR10-Pro + USB-AC): record
# short clips and print peak/RMS — no speaker / aplay required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECORD_SECONDS="${RECORD_SECONDS:-4}"
# Space-separated ALSA capture devices (defaults match two GeneralPlus cards).
MIC_DEVICES="${MIC_DEVICES:-hw:0,0 hw:1,0}"
# Mono 44.1 kHz matches common USB-AC defaults; use plughw:… if the device rejects hw:.
SAMPLE_RATE="${SAMPLE_RATE:-44100}"
OUT_DIR="${OUT_DIR:-/tmp}"
# If set (e.g. 500), jetson_mic_peak_check.py exits non-zero when capture looks silent.
MIN_PEAK="${MIN_PEAK:-0}"
# Hard cap so a stuck arecord cannot hang CI or SSH sessions.
ARECORD_TIMEOUT_S=$((RECORD_SECONDS + 20))

echo "Billiards-AI headless mic test (no playback)"
echo "  RECORD_SECONDS=$RECORD_SECONDS SAMPLE_RATE=$SAMPLE_RATE"
echo "  MIC_DEVICES=$MIC_DEVICES"
echo ""

for dev in $MIC_DEVICES; do
  safe="${dev//[^a-zA-Z0-9]/_}"
  wav="${OUT_DIR}/billiards_mic_${safe}.wav"
  echo "---- $dev -> $wav"
  if ! /usr/bin/timeout --signal=KILL "${ARECORD_TIMEOUT_S}s" \
    /usr/bin/arecord -q -D "$dev" -f S16_LE -r "${SAMPLE_RATE}" -c 1 -d "${RECORD_SECONDS}" "$wav"; then
    echo "  arecord failed for $dev (wrong -D?, cable, or permissions)" >&2
    continue
  fi
  if [[ "${MIN_PEAK}" != "0" ]]; then
    /usr/bin/python3 "${ROOT}/scripts/jetson_mic_peak_check.py" "$wav" --min-peak "${MIN_PEAK}"
  else
    /usr/bin/python3 "${ROOT}/scripts/jetson_mic_peak_check.py" "$wav"
  fi
done

echo ""
echo "Done. If peak_abs stays very low on one path, try the other USB port or"
echo "  arecord -D plughw:0,0 …  Copy WAVs to a machine with headphones to listen."
