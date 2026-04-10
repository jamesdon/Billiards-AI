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
  3: rack
EOF
```

## Minimal dataset bootstrap checklist (zero to first model)

Use this to get a first usable detector quickly.

1. Capture source video/images on your target table and camera setup.
2. Extract candidate frames (or label still images directly).
3. Label `ball` first; add `person`, `cue_stick`, and `rack` once baseline works.
4. Split train/val by session (not random frame-level only) to avoid leakage.
5. Train YOLO baseline.
6. Export ONNX.
7. Run Phase 3 and collect failures.
8. Add hard examples, retrain, repeat.

Recommended starter volume:

- **Ball-only baseline**: 300-800 labeled images
- **Ball + person + cue_stick + rack**: 1000-2500 labeled images
- **Val split**: 15-20% (from different sessions/lighting when possible)

## Can I train by hitting balls on my pool table?

Yes. That is a good approach and usually gives the best domain match.

Capture real play sequences:

- break shots
- slow rolls
- clustered balls
- rail shots
- pocket approach and pocketing
- player leaning/occluding balls
- cue stick near cue ball and across table
- between-rack setup moments where the triangle/rack is visible
- concession/end-of-match situations where balls stop and rack appears before formal final shot

Do multiple sessions:

- day and night lighting
- different camera exposure settings
- small camera angle shifts

## What should images look like? How close up?

Prefer the same framing used in runtime:

- full table visible (or the exact operational crop)
- camera fixed at production position
- consistent resolution with runtime (or proportional downsample)

Practical composition guidance:

- balls should generally be at least ~12-20 px diameter in labeled frames
- include both sparse and dense ball layouts
- include empty-table and low-motion frames occasionally
- avoid only dramatic close-ups; model must learn full-scene context

Do **not** train only on close-up ball crops if inference is on full table frames.

## Labeling tools (common options)

- CVAT (self-hosted/open-source, strong QA workflows)
- Label Studio (flexible workflows)
- Roboflow annotation tools (fast bootstrap and export convenience)

Use consistent class naming and IDs:

- `0: ball`
- `1: person`
- `2: cue_stick`
- `3: rack`

## Public datasets you can leverage

Yes, but treat them as supplemental data. Domain mismatch is common.

Good sources to explore:

- Roboflow Universe billiards/pool datasets (various projects and label schemas)
- public billiards/snooker academic datasets and GitHub repos

Best practice:

1. Normalize classes to your schema (`ball/person/cue_stick`).
2. Merge with your own table/camera data.
3. Prioritize your in-domain data in later fine-tuning rounds.
4. Validate on your own held-out sessions before Phase 3 sign-off.

## Helpful frame extraction tip

If you capture long videos, extract frames at low frequency first (for diversity):

```bash
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/images/raw"
ffmpeg -i "/absolute/path/to/session.mp4" -vf "fps=2" "/home/$USER/Billiards-AI/data/datasets/billiards/images/raw/%06d.jpg"
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

