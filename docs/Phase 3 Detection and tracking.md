# Phase 3: Detection and tracking

## Goal

Verify ONNX detection and multi-track stability.

## 1) Prepare class map

```bash
cd "/home/$USER/Billiards-AI"
cat > "/home/$USER/Billiards-AI/class_map.json" <<'EOF'
{
  "0": "ball",
  "1": "person",
  "2": "cue_stick"
}
EOF
```

## 2) Run Phase 3 verification script (recommended)

This script performs:

- baseline run at `--detect-every-n 2`
- sweep runs at `--detect-every-n 1` and `--detect-every-n 3`
- MJPEG readiness checks for each run
- per-run logs under repo root: `.phase3_n1.log`, `.phase3_n2.log`, `.phase3_n3.log`

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
MODEL_PATH="/ABSOLUTE/PATH/TO/model.onnx" \
CLASS_MAP_PATH="/home/$USER/Billiards-AI/class_map.json" \
CAMERA_SOURCE="csi" \
CSI_SENSOR_ID=0 \
MJPEG_PORT=8080 \
EDGE_TIMEOUT_SECONDS=1200 \
"/home/$USER/Billiards-AI/scripts/phase3.sh"
```

## 3) Optional manual single-run command

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python -m edge.main \
  --camera csi \
  --csi-sensor-id 0 \
  --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" \
  --class-map "/home/$USER/Billiards-AI/class_map.json" \
  --detect-every-n 2 \
  --mjpeg-port 8080
```

## Pass criteria

- no detector/tracker crashes
- IDs remain stable for moving balls/players/sticks in normal play
- sweep logs exist for `n=1,2,3` and each run reaches MJPEG endpoint

