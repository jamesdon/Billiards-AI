# Phase 3: Detection and tracking

## Goal

Verify ONNX detection and multi-track stability.

**Prerequisite note:** Phase 3 assumes `models/model.onnx` and `models/class_map.json` are already on the device. **Training that model is a separate, optional step** (see `docs/MODEL_OPTIMIZATION.md`); day-to-day new installs typically **reuse the same exported model** and only run calibration plus this phase as smoke.

## 1) Prepare class map (canonical path)

All detector assets live under `models/`. The repo includes `models/class_map.json`; override only if your ONNX uses different indices or labels.

```bash
cd "/home/$USER/Billiards-AI"
mkdir -p "/home/$USER/Billiards-AI/models"
# Optional: only if you are not using the committed template
cat > "/home/$USER/Billiards-AI/models/class_map.json" <<'EOF'
{
  "0": "ball",
  "1": "person",
  "2": "cue_stick",
  "3": "rack"
}
EOF
```

## 2) Bootstrap a starter ONNX model (from scratch)

If you are starting from scratch and do not yet have a trained billiards model,
you must create one before running Phase 3. This is a bootstrap path to get a
valid detector artifact quickly (accuracy will depend on your dataset quality).

### 2a) Train a small YOLO model (example with Ultralytics)

On a machine with GPU and training data:

```bash
python3 -m pip install -U ultralytics
yolo detect train data="/ABSOLUTE/PATH/TO/billiards-data.yaml" model="yolov8n.pt" imgsz=640 epochs=100 batch=16
```

Expected labels in dataset should align with your class map:

- `0: ball`
- `1: person`
- `2: cue_stick`
- `3: rack` (triangle/diamond rack object, used for concession/end-of-rack fallback)

### 2b) Export the trained model to ONNX

```bash
yolo export model="runs/detect/train/weights/best.pt" format=onnx imgsz=640
```

Copy the exported ONNX to the Orin Nano:

```bash
mkdir -p "/home/$USER/Billiards-AI/models"
cp "/ABSOLUTE/PATH/TO/best.onnx" "/home/$USER/Billiards-AI/models/model.onnx"
```

### 2c) Verify model file exists on device

```bash
/usr/bin/ls -lh "/home/$USER/Billiards-AI/models/model.onnx"
```

## 3) Run Phase 3 verification script (recommended)

This script performs:

- baseline run at `--detect-every-n 2`
- sweep runs at `--detect-every-n 1` and `--detect-every-n 3`
- MJPEG readiness checks for each run
- per-run logs under repo root: `.phase3_n1.log`, `.phase3_n2.log`, `.phase3_n3.log`

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
MODEL_PATH="/ABSOLUTE/PATH/TO/model.onnx" \
CLASS_MAP_PATH="/home/$USER/Billiards-AI/models/class_map.json" \
CAMERA_SOURCE="csi" \
CSI_SENSOR_ID=0 \
CSI_FLIP_METHOD=6 \
MJPEG_PORT=8080 \
EDGE_TIMEOUT_SECONDS=1200 \
"/home/$USER/Billiards-AI/scripts/phase3.sh"
```

## 4) Optional manual single-run command

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python -m edge.main \
  --camera csi \
  --csi-sensor-id 0 \
  --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" \
  --class-map "/home/$USER/Billiards-AI/models/class_map.json" \
  --detect-every-n 2 \
  --mjpeg-port 8080
```

## Pass criteria

- no detector/tracker crashes
- IDs remain stable for moving balls/players/sticks in normal play
- sweep logs exist for `n=1,2,3` and each run reaches MJPEG endpoint

