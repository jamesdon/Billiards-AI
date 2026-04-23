# Model optimization (ONNX → TensorRT)

## Training vs deploying a new device

**Training and billiards-specific tuning are optional and usually done once** (or occasionally when you want a better shared detector). You build a labeled dataset, train a YOLO-family model, export ONNX, and iterate on hard examples until metrics and Phase 3 runs look good.

**Normal setup of additional tables or edge devices does not repeat training.** You reuse the same artifacts under a **single directory**:

- `models/model.onnx` — detector weights (not committed; override with `MODEL_PATH` / Docker `MODEL_PATH`)
- `models/class_map.json` — same class indices as training (`0..4` → `ball`, `person`, `cue_stick`, `rack`, `pockets`; committed template in repo)

`scripts/phase3.sh`, `phase4.sh`, and `phase9.sh` default `CLASS_MAP_PATH` to `$PROJECT_ROOT/models/class_map.json`. Jetson-family Docker (Orin Nano compose) mounts `./models` at `/models` and uses the same filenames by default.

Per-device variation is handled by **calibration** (homography, pocket geometry), not by retraining the detector, unless the camera or scene is radically different from what the model saw.

The sections below describe dataset → train → export → optional TensorRT. Treat that whole path as **model authoring**; treat copying ONNX into `models/` plus running Phase 3 smoke as **device bring-up**.

## Why one `ball` class in the detector (Phase 3) vs type in Phase 4

This is a **project default**, not a hard limit of YOLO.

**What the codebase does today:** the detector finds **generic ball boxes** at full-table resolution; `edge/pipeline.py` then tracks them and `edge/classify/ball_classifier.py` infers **type** (cue vs solids vs stripes, game-dependent) from **cropped ROIs** with cheap HSV-style features and temporal smoothing. That is the Phase 4 layer in `docs/Phase 4 Classification and identity.md`.

**Why split “where” from “what”:**

- **Labeling cost** — every frame needs tight boxes; adding 6–16 ball *types* multiplies annotation and review time.
- **Full-frame difficulty** — at 720p table-wide views, balls are small and visually similar; a single “ball” head is usually easier to stabilize than many sibling classes fighting the same anchors.
- **Iteration speed** — get reliable **presence + motion** first (rules, pockets, collisions care about geometry); refine **appearance** once crops are trustworthy.
- **Runtime** — one detector pass + small ROI work scales better on edge SoCs (Orin Nano included) than pushing all semantics into the largest model.

**You can still train more ball types in YOLO** if you want: extend `names` / labels / `models/class_map.json` (e.g. `cue_ball`, `solid`, `stripe`, `eight_ball`) and widen `ball_dets` filtering in `edge/pipeline.py` so those labels enter the ball tracker. That is extra integration and dataset work, not a merge of “phases” by itself.

## Optional: one multiclass detector (train your own)

For **per-ball identity from the detector** (instead of ROI heuristics), train a **single YOLO head** with one index per class you care about, for example:

- `ball_1` … `ball_15`, `ball_cue`, `eight`, `nine` (game-specific), plus existing `person`, `cue_stick`, `rack`.

Steps:

1. Label in YOLO with **contiguous** class indices; keep `models/class_map.json` as the **authoritative** `index → label string` map (same strings the ONNX postprocess emits).
2. Expand `ball_dets` filtering in `edge/pipeline.py` so every label that should participate in **ball tracking** is included (today it whitelists generic names).
3. Decide whether **Phase 4** `BallClassifier` runs only when `detector_hint` is missing, or is skipped entirely when the detector already emits ball type.
4. Expect **more labeling work** and stricter train/val splits by session; gains are fewer ROI mistakes and cleaner **voice “highlight the 8 ball”** hooks tied to detections.

**Merging Phase 3 and Phase 4:** the **phase documents** are delivery checkpoints (detection vs identity), not two incompatible algorithms. You might *personally* combine work into one training push (richer detector + less ROI classifier), but the repo keeps them separate so you can ship **tracking without** perfect type classification, and upgrade types later without retraining the whole detector if you choose the two-stage design.

## Billiards detector: training walkthrough

Follow this once (or when refreshing the shared model). All paths use `"/home/$USER/Billiards-AI"` as the project root; substitute yours.

1. **Class contract** — Keep `models/class_map.json` in sync with your YOLO dataset `names`. The repo template is five classes in order `ball`, `person`, `cue_stick`, `rack`, `pockets`. If you train with fewer classes, remove unused keys from the JSON **and** renumber your dataset so indices stay contiguous from `0` (or keep a dedicated class map that matches exactly what the ONNX head outputs).

2. **Dataset layout (YOLO)** — Under `data/datasets/billiards/`, use `images/train`, `images/val`, `labels/train`, `labels/val` with matching stem names (e.g. `frame_000123.jpg` + `frame_000123.txt`). See **Required input** below for the `billiards-data.yaml` example; its `names:` block must match `class_map.json`.

3. **Label quality** — Start with balls; add people, cue sticks, and rack frames as in the checklist later in this doc. Split train/val by **session** where possible.

4. **Environment** — In the project venv: install **`requirements-train.txt`** after `requirements.txt` so NumPy stays pinned with `numpy<2` alongside distro OpenCV on Jetson-family devices and matplotlib is venv-local (avoids Ultralytics importing system matplotlib against NumPy 2). On a desktop GPU you can still use the same file. JetPack 5 (Orin) is usually less brittle than JetPack 4 Maxwell stacks, but the pin avoids surprise ABI drift. See `docs/ORIN_NANO_TRAIN_AND_TEST.md` for the full on-device sequence.

5. **Train** — From the project root (paths as in **Option A** / **Option B** below), e.g.  
   `yolo detect train data=".../billiards-data.yaml" model=yolov8n.pt imgsz=640 epochs=100 batch=16`  
   Adjust `batch` and `workers` if you train on the Orin Nano (or any smaller edge GPU).

6. **Export ONNX** —  
   `yolo export model="runs/detect/train/weights/best.pt" format=onnx imgsz=640`  
   (use the actual run path Ultralytics prints).

7. **Install weights** — Copy the exported file to the canonical name:  
   `cp runs/detect/train/weights/best.onnx models/model.onnx`  
   (`*.onnx` is gitignored; this file lives only on disk or in your release storage.)

8. **Verify** — Run `scripts/phase3.sh` with defaults, or a short smoke:  
   `python -m edge.main --camera csi --onnx-model models/model.onnx --class-map models/class_map.json --detect-every-n 2 --mjpeg-port 8001`  
   Tune `conf_thres` / training data if boxes are noisy; see **Runtime knobs** and Phase 3 docs.

## Do I have to train on another machine?

No. You can train on Jetson Orin Nano directly, but it is usually much slower than a desktop/datacenter GPU.

- **Train on Orin Nano**: acceptable for small datasets and early iteration (much more comfortable than old Nano).
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
  4: pockets
EOF
```

On-device checklist: `docs/ORIN_NANO_TRAIN_AND_TEST.md` (paths like `/home/$USER/Billiards-AI`, NumPy/OpenCV guardrails, `yolo` + pytest + phases).

## Minimal dataset bootstrap checklist (zero to first model)

Use this to get a first usable detector quickly.

1. Capture source video/images on your target table and camera setup.
2. Extract candidate frames (or label still images directly).
3. Label `ball` first; add `person`, `cue_stick`, `rack`, and `pockets` once baseline works (or merge public data; see batch merge scripts).
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
- `4: pockets`

## Public datasets you can leverage

Yes, but treat them as supplemental data. Domain mismatch is common.

Good sources to explore:

- Roboflow Universe billiards/pool datasets (various projects and label schemas)
- public billiards/snooker academic datasets and GitHub repos

**Batch download + class audit (this repo):** copy `scripts/roboflow_universe_manifest.example.yaml` to `scripts/roboflow_universe_manifest.yaml`, add `imports:` rows (workspace, project, version, dirname), set `ROBOFLOW_API_KEY`, then run `python3 scripts/roboflow_universe_pull.py --manifest scripts/roboflow_universe_manifest.yaml`. Summarize labels and heuristic mapping hints with `python3 scripts/yolo_import_class_report.py --imports-dir data/datasets/_imports` (or pass explicit import paths).

**Reproduce everything in one command** (uses `scripts/roboflow_universe_manifest.yaml` and `scripts/roboflow_merge_batch.yaml` if you created them; otherwise the committed `*.example.yaml` files): `export ROBOFLOW_API_KEY='…' && bash scripts/universe_dataset_pipeline.sh`. That runs `jetson_prepare_yolo_dataset.sh`, downloads every import in the manifest, then merges with `merge_yolo_imports_to_billiards.py --batch-yaml`. Add new datasets by editing both example YAMLs (or your copies) and re-run.

### Finding the Roboflow dataset `version:` (what to put in the manifest)

Universe **landing URLs** (e.g. `https://universe.roboflow.com/workspace/project`) often **do not** show a reliable version in the address bar, and the UI changes over time—so “look at `/dataset/N` in the URL” is **not** guaranteed.

**What works (in order of reliability):**

1. **Show download code (matches the Python API exactly)** — Per [Roboflow’s own steps](https://docs.roboflow.com/universe/download-a-universe-dataset): open the project on Universe → left sidebar **Dataset** → **Download Dataset** → **Show download code**. The generated snippet includes `project.version(N)` (or `dataset.version(N)` in some templates). The integer **`N`** is the `version:` value for `roboflow_universe_pull.py` / your manifest.
2. **`data.yaml` inside an export you already downloaded** — Under the `roboflow:` block, `version:` is the dataset version (same as the API).
3. **Try `version: 1` first** — Many public snapshots are still version `1`; if the API errors, use **Show download code** on that project to read the real `N`.

If `pull.py` fails on a row, fix **`version:`** for that row only; workspace and project slugs must match the Universe URL path (`/workspace-slug/project-slug`).

**Merge several imports into training data:** after `jetson_prepare_yolo_dataset.sh`, run `python3 scripts/merge_yolo_imports_to_billiards.py data/datasets/_imports/<dir1> data/datasets/_imports/<dir2> ...` — prefixes filenames per import to avoid collisions; default remaps all classes to `0` (ball). Re-run training after adding data; avoid merging the same import twice (duplicate images).

**Imports with pockets (`bag1`…`bag6`) + per-ball ids** (e.g. Universe `jdq/table2-kfsub`): map **bags → class `4` `pockets`** (not `ball`). Use `python3 scripts/merge_yolo_imports_to_billiards.py --batch-yaml …` with `auto_remap_from_yaml: true`, or explicit `--map-json` / `--only-source-ids` as before. Roboflow often names pockets `bag*`; your runtime label is **`pockets`** per `class_map.json`.

Best practice:

1. Normalize classes to your schema (`ball/person/cue_stick`).
2. Merge with your own table/camera data.
3. Prioritize your in-domain data in later fine-tuning rounds.
4. Validate on your own held-out sessions before Phase 3 sign-off.

## Live CSI capture (same camera as production)

To build a dataset **from the live table** (no pre-recorded video), save frames with:

`cd ~/Billiards-AI && bash scripts/jetson_capture_training_frames.sh --count 300 --stride 20 --prefix session1`

See `docs/ORIN_NANO_TRAIN_AND_TEST.md` (live table → training). You still add YOLO `.txt` labels and split train/val before `yolo train`.

## Helpful frame extraction tip

If you capture long videos, extract frames at low frequency first (for diversity):

Install ffmpeg first (Ubuntu / Jetson image):

```bash
sudo /usr/bin/apt-get update || true
sudo /usr/bin/apt-get install -y ffmpeg
```

```bash
mkdir -p "/home/$USER/Billiards-AI/data/datasets/billiards/images/raw"
ffmpeg -i "/absolute/path/to/session.mp4" -vf "fps=2" "/home/$USER/Billiards-AI/data/datasets/billiards/images/raw/%06d.jpg"
```

## Option A: Train directly on Jetson Orin Nano

Use this if you do not have another GPU machine available.

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip install -r "/home/$USER/Billiards-AI/requirements-train.txt"
```

On **Apple Silicon (macOS/arm64)**, prefer `bash scripts/jetson_yolo_train.sh`: it uses higher default `epochs` / `batch` / `workers` than on Jetson (override with `YOLO_EPOCHS`, `YOLO_BATCH`, `YOLO_WORKERS`).

Train on Jetson (conservative defaults; increase `batch` on Orin if memory allows):

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

## Option B: Train on another machine, run on Orin Nano

This is usually the fastest path overall.

On training machine:

```bash
python3 -m pip install -U ultralytics
yolo detect train data="/ABSOLUTE/PATH/TO/billiards-data.yaml" model="yolov8n.pt" imgsz=640 epochs=100 batch=16
yolo export model="/ABSOLUTE/PATH/TO/runs/detect/train/weights/best.pt" format=onnx imgsz=640
```

Copy artifact to Orin Nano:

```bash
mkdir -p "/home/$USER/Billiards-AI/models"
scp "/ABSOLUTE/PATH/TO/best.onnx" "$USER@<ORIN_NANO_IP>:/home/$USER/Billiards-AI/models/model.onnx"
```

Verify on Orin Nano:

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
- `4`: `pockets` (learned pocket regions; Roboflow exports often use `bag*` names — remap to this id)

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
  --mjpeg-port 8001
```

## Detector choice

Use a small model class (YOLOv8n / YOLOv5n / custom tiny) trained for:

- billiard balls (optionally per-type labels)
- cue ball
- optionally cue stick

## Export to ONNX

Preferred: export with static input shape (e.g., 416×416) and FP16 when available.

## ONNXRuntime baseline

ONNXRuntime is the default runtime in this repo for portability. On Orin Nano use a Jetson **aarch64** build with CUDA/TensorRT EPs when you want GPU acceleration without converting engines yourself.

## TensorRT (recommended on Jetson Orin)

Convert ONNX to TensorRT engine:

- FP16 is usually the best trade-off on Orin-class hardware (ample headroom vs old Maxwell Nano).
- INT8 requires calibration and can be fragile; use only if needed.

## Runtime knobs

- inference every N frames (2–3)
- smaller input resolution
- reduce max detections and NMS candidates

