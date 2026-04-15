# Model optimization (ONNX → TensorRT)

## Training vs deploying a new device

**Training and billiards-specific tuning are optional and usually done once** (or occasionally when you want a better shared detector). You build a labeled dataset, train a YOLO-family model, export ONNX, and iterate on hard examples until metrics and Phase 3 runs look good.

**Normal setup of additional tables or Jetsons does not repeat training.** You reuse the same artifacts under a **single directory**:

- `models/model.onnx` — detector weights (not committed; override with `MODEL_PATH` / Docker `MODEL_PATH`)
- `models/class_map.json` — same class indices as training (`0..3` → `ball`, `person`, `cue_stick`, `rack`; committed template in repo)

`scripts/phase3.sh`, `phase4.sh`, and `phase9.sh` default `CLASS_MAP_PATH` to `$PROJECT_ROOT/models/class_map.json`. Jetson Docker mounts `./models` at `/models` and uses the same filenames by default.

Per-device variation is handled by **calibration** (homography, pocket geometry), not by retraining the detector, unless the camera or scene is radically different from what the model saw.

The sections below describe dataset → train → export → optional TensorRT. Treat that whole path as **model authoring**; treat copying ONNX into `models/` plus running Phase 3 smoke as **device bring-up**.

## Billiards detector: training walkthrough

Follow this once (or when refreshing the shared model). All paths use `"/home/$USER/Billiards-AI"` as the project root; substitute yours.

1. **Class contract** — Keep `models/class_map.json` in sync with your YOLO dataset `names`. The repo template is four classes in order `ball`, `person`, `cue_stick`, `rack`. If you train with fewer classes, remove unused keys from the JSON **and** renumber your dataset so indices stay contiguous from `0` (or keep a dedicated class map that matches exactly what the ONNX head outputs).

2. **Dataset layout (YOLO)** — Under `data/datasets/billiards/`, use `images/train`, `images/val`, `labels/train`, `labels/val` with matching stem names (e.g. `frame_000123.jpg` + `frame_000123.txt`). See **Required input** below for the `billiards-data.yaml` example; its `names:` block must match `class_map.json`.

3. **Label quality** — Start with balls; add people, cue sticks, and rack frames as in the checklist later in this doc. Split train/val by **session** where possible.

4. **Environment** — In the project venv: install **`requirements-train.txt`** after `requirements.txt` so NumPy stays pinned with `numpy<2` on Jetson and matplotlib is venv-local (avoids Ultralytics importing system matplotlib against NumPy 2). On a desktop GPU you can still use the same file. See `docs/JETSON_NANO_TRAIN_AND_TEST.md` for the full Nano sequence.

5. **Train** — From the project root (paths as in **Option A** / **Option B** below), e.g.  
   `yolo detect train data=".../billiards-data.yaml" model=yolov8n.pt imgsz=640 epochs=100 batch=16`  
   Adjust `batch` and `workers` if you train on Jetson.

6. **Export ONNX** —  
   `yolo export model="runs/detect/train/weights/best.pt" format=onnx imgsz=640`  
   (use the actual run path Ultralytics prints).

7. **Install weights** — Copy the exported file to the canonical name:  
   `cp runs/detect/train/weights/best.onnx models/model.onnx`  
   (`*.onnx` is gitignored; this file lives only on disk or in your release storage.)

8. **Verify** — Run `scripts/phase3.sh` with defaults, or a short smoke:  
   `python -m edge.main --camera csi --onnx-model models/model.onnx --class-map models/class_map.json --detect-every-n 2 --mjpeg-port 8080`  
   Tune `conf_thres` / training data if boxes are noisy; see **Runtime knobs** and Phase 3 docs.

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

Create the dataset YAML with a **real absolute** `path:` (never a literal `$USER` string inside the file; Ultralytics will fail if `path:` is wrong).

Preferred (writes paths from your actual project root):

```bash
cd "/home/$USER/Billiards-AI"
chmod +x scripts/bootstrap_billiards_dataset.sh
PROJECT_ROOT="/home/$USER/Billiards-AI" ./scripts/bootstrap_billiards_dataset.sh
grep '^path:' "/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml"
```

Manual alternative (note **unquoted** `EOF` so `$USER` expands into the YAML):

```bash
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/images/train"
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/images/val"
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/labels/train"
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/labels/val"
cat > "/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml" <<EOF
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

Jetson-only checklist: `docs/JETSON_NANO_TRAIN_AND_TEST.md` (paths like `/home/$USER/Billiards-AI`, NumPy/matplotlib fixes, `yolo` + pytest + phases).

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

## Live CSI capture (same camera as production)

To build a dataset **from the live table** (no pre-recorded video), save frames with:

`cd ~/Billiards-AI && bash scripts/jetson_capture_training_frames.sh --count 300 --stride 20 --prefix session1`

See `docs/JETSON_NANO_TRAIN_AND_TEST.md` (live table → training). You still add YOLO `.txt` labels and split train/val before `yolo train`.

## Helpful frame extraction tip

If you capture long videos, extract frames at low frequency first (for diversity):

Install ffmpeg first (Jetson/Ubuntu):

```bash
sudo /usr/bin/apt-get update || true
sudo /usr/bin/apt-get install -y ffmpeg
```

```bash
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/images/raw"
ffmpeg -i "/absolute/path/to/session.mp4" -vf "fps=2" "/home/$USER/Billiards-AI/data/datasets/billiards/images/raw/%06d.jpg"
```

## Option A: Train directly on Jetson Nano/Orin

Use this if you do not have another GPU machine available.

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip install -r "/home/$USER/Billiards-AI/requirements-train.txt"
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

Train a small YOLO-family detector with classes aligned to `models/class_map.json`:

- `0`: `ball`
- `1`: `person` (recommended for identity tracking)
- `2`: `cue_stick` (recommended for identity tracking)
- `3`: `rack` (triangle/diamond rack; pipeline + rules use this where applicable)

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
  --class-map "/home/$USER/Billiards-AI/models/class_map.json" \
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

