# Model optimization (ONNX → TensorRT)

## From-scratch baseline model procedure (required before Phase 3+)

If you are starting from scratch, there is no detector artifact in this repo.
You must create/export `model.onnx` before Phase 3, 4, or 9.

### 1) Train a lightweight detector

Train a small YOLO-family detector with classes aligned to `class_map.json`:

- `0`: `ball`
- `1`: `person` (optional but recommended for identity tracking)
- `2`: `cue_stick` (optional but recommended for identity tracking)

### 2) Export to ONNX

Export the trained model with a static input shape (example 416x416).
Preferred export settings:

- opset: 12+ (14 common)
- static input shape
- FP16 where available

### 3) Place artifact in expected project path

```bash
cd "/home/$USER/Billiards-AI"
mkdir -p "/home/$USER/Billiards-AI/models"
cp "/absolute/path/to/your/exported/model.onnx" "/home/$USER/Billiards-AI/models/model.onnx"
ls -lh "/home/$USER/Billiards-AI/models/model.onnx"
```

### 4) Sanity run before full phase

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 60 python -m edge.main \
  --camera csi \
  --csi-sensor-id 0 \
  --onnx-model "/home/$USER/Billiards-AI/models/model.onnx" \
  --class-map "/home/$USER/Billiards-AI/class_map.json" \
  --detect-every-n 2 \
  --mjpeg-port 8080
```

## Detector choice

Use a small model class (YOLOv8n / YOLOv5n / custom tiny) trained for:

- billiard balls (optionally per-type labels)
- cue ball
- optionally cue stick

## Export to ONNX

Preferred: export with static input shape (e.g., 416×416) and FP16 when available.

## ONNXRuntime baseline

ONNXRuntime is the default runtime in this repo for portability. On Jetson you’ll want the Jetson-compatible build.

## TensorRT (recommended on Jetson)

Convert ONNX to TensorRT engine:

- FP16 is usually the best trade-off on Nano.
- INT8 requires calibration and can be fragile; use only if needed.

## Runtime knobs

- inference every N frames (2–3)
- smaller input resolution
- reduce max detections and NMS candidates

