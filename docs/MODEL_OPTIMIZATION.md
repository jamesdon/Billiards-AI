# Model optimization (ONNX → TensorRT)

## Do I have to train on another machine?

No. You can train on Jetson Nano/Orin directly, but it is usually much slower.

- **Train on Nano/Orin**: acceptable for small datasets and early iteration.
- **Train on a stronger GPU machine**: recommended for faster iteration and larger datasets.
- In both cases, the runtime artifact consumed by this project is the same:
  - `"/home/$USER/Billiards-AI/models/model.onnx"`

## Required input (for any training machine)

You need a labeled detection dataset in YOLO format.

Recommended project-local location:

- `"/home/$USER/Billiards-AI/data/datasets/billiards/images/train"`
- `"/home/$USER/Billiards-AI/data/datasets/billiards/images/val"`
- `"/home/$USER/Billiards-AI/data/datasets/billiards/labels/train"`
- `"/home/$USER/Billiards-AI/data/datasets/billiards/labels/val"`

Create YAML:

```bash
cat > "/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml" <<'EOF'
path: /home/$USER/Billiards-AI/data/datasets/billiards
train: images/train
val: images/val
names:
  0: ball
  1: person
  2: cue_stick
EOF
```

## Option A: Train directly on Jetson Nano/Orin

Use this if you do not have another GPU machine available.

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -U ultralytics
```

Train (Jetson-friendly defaults):

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
yolo detect train \
  data="/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml" \
  model="yolov8n.pt" \
  imgsz=640 \
  epochs=100 \
  batch=4 \
  workers=2
```

Export ONNX:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
yolo export model="/home/$USER/Billiards-AI/runs/detect/train/weights/best.pt" format=onnx imgsz=640
mkdir -p "/home/$USER/Billiards-AI/models"
cp "/home/$USER/Billiards-AI/runs/detect/train/weights/best.onnx" "/home/$USER/Billiards-AI/models/model.onnx"
ls -lh "/home/$USER/Billiards-AI/models/model.onnx"
```

## Option B: Train on another machine, run on Nano

This is usually the fastest path overall.

On training machine:

```bash
python3 -m pip install -U ultralytics
yolo detect train data="/ABSOLUTE/PATH/TO/billiards-data.yaml" model="yolov8n.pt" imgsz=640 epochs=100 batch=16
yolo export model="/ABSOLUTE/PATH/TO/runs/detect/train/weights/best.pt" format=onnx imgsz=640
```

Copy artifact to Nano:

```bash
mkdir -p "/home/$USER/Billiards-AI/models"
scp "/ABSOLUTE/PATH/TO/best.onnx" "$USER@<NANO_IP>:/home/$USER/Billiards-AI/models/model.onnx"
```

Verify on Nano:

```bash
ls -lh "/home/$USER/Billiards-AI/models/model.onnx"
```

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

