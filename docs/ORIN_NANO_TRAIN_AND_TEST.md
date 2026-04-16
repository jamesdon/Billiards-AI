# Jetson Orin Nano: train YOLO on-device, then run tests (Billiards-AI)

## Platform baseline (read once)

This repo targets **NVIDIA Jetson Orin Nano** on **JetPack 5.x** (Ubuntu 20.04 / 22.04 depending on image; **Python 3.8–3.10** is typical, with 3.10 common on newer stacks). That is a different generation than Jetson Nano + JetPack 4.x: **Ampere-class GPU** vs Maxwell, **much higher compute**, **better ONNX Runtime and TensorRT packaging**, a **more stable GStreamer + CSI stack**, and generally **less fragile** Python wheels than the old Maxwell world.

**Strategy (unchanged and still correct):** ONNX Runtime as the portable baseline → **TensorRT FP16** for production; **CSI via GStreamer**; **edge-first standalone** pipeline; **YOLOv8n**-class detector; **detect → classify** split (generic `ball` + HSV ROI classifier); **IoU tracker** baseline; **homography** table coordinates.

**NumPy / OpenCV:** JetPack 5 does not magically eliminate ABI mismatches if pip pulls **NumPy 2.x** against a **distro `python3-opencv`** built for NumPy 1.x. This repo still pins **`numpy<2`** in training flows and keeps **distro OpenCV + GStreamer** (not `opencv-python` wheels) on device—see `docs/DEPLOYMENT_JETSON.md` and `scripts/common.sh`. On Orin the path is usually *smoother*, but the guardrails stay.

---

## Why “nothing happened” when you pasted from this file

Markdown **code fences** are the lines that look like three backticks (often shown as ` ```bash ` at the start and ` ``` ` at the end). **Those backtick lines are not shell commands.** If you paste them into the terminal, bash does not run `git pull` or `pip`.

**Use one of the two options below** (A is recommended).

---

## Option A (recommended): one line per step, no Markdown fences

Open **bash** on the Orin Nano. `cd` into your clone (default layout: `~/Billiards-AI`). Each line below is a **full command**—copy the line only (no backticks from Markdown, no ` ```bash ` line).

**`git pull` only works inside the repo.** If you see `fatal: not a git repository`, you ran it from `~` or another folder; run `cd ~/Billiards-AI` then `git pull` (or rely on `jetson_train_env.sh`, which runs `git pull` after `cd`).

Plain-text cheat sheet (same commands, no Markdown): `scripts/JETSON_ONE_LINERS.txt` — run `cat scripts/JETSON_ONE_LINERS.txt` and paste lines that do **not** start with `#`.

If your repo lives somewhere else, set `PROJECT_ROOT` first, e.g. `export PROJECT_ROOT=/home/jdonn/Billiards-AI` (scripts read this via `scripts/common.sh`).

### Where training images come from (the repo does not include them)

**This project does not ship a photo dataset.** You train on **your own** pictures of **your** table from **your** production camera angle (or the same crop you will use live). Typical sources:

1. **Record or grab frames from the CSI camera** on the Orin Nano (same rig as Phase 3/4): save stills or short videos to disk, then copy JPEG/PNG frames into `data/datasets/billiards/images/train` and `.../images/val`. Use different nights/sessions for val when you can.
2. **Extract frames from a video** you shot over the table (see `docs/MODEL_OPTIMIZATION.md` → “Helpful frame extraction tip” for an `ffmpeg` example writing into `data/datasets/billiards/images/...`).
3. **Import** a YOLO-format dataset (e.g. export from Roboflow, or another billiards project) and merge images + labels into those same `images/` and `labels/` folders—**renumber classes** so they match `models/class_map.json` (`0` ball … `3` rack).

**Where on disk:** after `jetson_prepare_yolo_dataset.sh`, use:

- `~/Billiards-AI/data/datasets/billiards/images/train` and `.../images/val`
- `~/Billiards-AI/data/datasets/billiards/labels/train` and `.../labels/val`

For every `something.jpg` (or `.png`), YOLO expects a matching `something.txt` in the **labels** split with one line per object: `class cx cy w h` (normalized 0–1). Create labels with a tool (CVAT, Label Studio, Roboflow, etc.); see `docs/MODEL_OPTIMIZATION.md` for composition, class list, and how much data to aim for.

### Live table → same training pipeline (record now, label, then `jetson_yolo_train.sh`)

Ultralytics **does not** continuously learn from the camera during `yolo train`; it still needs **saved** images plus labels. What you *can* do is **point the live CSI feed at the table**, save frames to disk, then label those frames—same camera and lighting as production.

**Several ball sets:** run a **separate capture** per set (or use a different `--prefix` / `--out-dir` per session), then mix those JPEGs into `images/train` and `images/val` when you split. Variety across sets improves the detector; ball **identity** (solid/stripe/…) is still Phase 4, not the detector class `ball`.

**Capture command** (from repo root, venv active—`jetson_capture_training_frames.sh` does both):

`cd ~/Billiards-AI && bash scripts/jetson_capture_training_frames.sh --count 300 --stride 20 --prefix stripes_night`

Defaults write under `data/datasets/billiards/images/capture/`. After labeling, move or copy a fraction of JPEGs + matching `.txt` files into `images/train` / `labels/train` and `images/val` / `labels/val` before training.

1. **Environment + pip installs**

   `cd ~/Billiards-AI && bash scripts/jetson_train_env.sh`

2. **Dataset dirs + `billiards-data.yaml`**

   `cd ~/Billiards-AI && bash scripts/jetson_prepare_yolo_dataset.sh`

3. **Train** — run only after you have added **your** images + `.txt` labels (see **“Where training images come from”** above).

   `cd ~/Billiards-AI && bash scripts/jetson_yolo_train.sh`

   Shorter run (example): `cd ~/Billiards-AI && YOLO_EPOCHS=10 YOLO_BATCH=2 bash scripts/jetson_yolo_train.sh`

4. **Export latest checkpoint to `models/model.onnx`**

   `cd ~/Billiards-AI && bash scripts/jetson_yolo_export_latest.sh`

5. **Pytest**

   `cd ~/Billiards-AI && bash scripts/jetson_pytest.sh`

6. **Phases 1 and 3**

   `cd ~/Billiards-AI && bash scripts/jetson_phases_1_3.sh`

7. **Edge CSI smoke** (runs until Ctrl+C)

   `cd ~/Billiards-AI && bash scripts/jetson_edge_smoke_csi.sh`

   Optional calib path: `cd ~/Billiards-AI && CALIB_PATH=/path/to/calibration.json bash scripts/jetson_edge_smoke_csi.sh`

Scripts use `PROJECT_ROOT` (default `/home/$USER/Billiards-AI` in `common.sh`). `~/Billiards-AI` is the same directory when your clone is under your home.

**Pip noise:** `jetson_train_env.sh` may print resolver warnings (e.g. packages “not installed” while they install, or old opencv vs numpy). If the script ends with `jetson_train_env.sh: OK`, the venv is in a good state for the next step.

---

## Option B: paste multi-line shell (advanced)

Only copy lines **between** the fences—**never** copy a line that is only three backticks. If your viewer selects the fences, delete them before Enter.

The blocks below are identical to what the `scripts/jetson_*.sh` files run; use Option A unless you are debugging.

### Block 1 (same as `jetson_train_env.sh`)

```bash
cd "/home/$USER/Billiards-AI"
git pull
test -d .venv || python3 -m venv --system-site-packages .venv
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip install -r "/home/$USER/Billiards-AI/requirements-train.txt"
```

### Block 2 (same as `jetson_prepare_yolo_dataset.sh`)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
chmod +x "/home/$USER/Billiards-AI/scripts/bootstrap_billiards_dataset.sh"
PROJECT_ROOT="/home/$USER/Billiards-AI" "/home/$USER/Billiards-AI/scripts/bootstrap_billiards_dataset.sh"
/usr/bin/grep '^path:' "/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml"
```

### Block 3 (same as `jetson_yolo_train.sh`)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
yolo detect train \
  data="/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml" \
  model="yolov8n.pt" \
  imgsz=640 \
  epochs=30 \
  batch=4 \
  workers=2 \
  project="/home/$USER/Billiards-AI/runs/detect"
```

### Block 4 (same as `jetson_yolo_export_latest.sh`)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
LATEST_PT="$(ls -t "/home/$USER/Billiards-AI/runs/detect/"*/weights/best.pt 2>/dev/null | head -1)"
if [[ -z "${LATEST_PT}" ]]; then echo "No training run found."; exit 1; fi
echo "Using: ${LATEST_PT}"
yolo export model="${LATEST_PT}" format=onnx imgsz=640
WEIGHTS_DIR="$(dirname "${LATEST_PT}")"
ONNX_OUT="${WEIGHTS_DIR}/best.onnx"
test -f "${ONNX_OUT}"
mkdir -p "/home/$USER/Billiards-AI/models"
cp "${ONNX_OUT}" "/home/$USER/Billiards-AI/models/model.onnx"
ls -lh "/home/$USER/Billiards-AI/models/model.onnx" "/home/$USER/Billiards-AI/models/class_map.json"
```

### Block 5–7

Use `jetson_pytest.sh`, `jetson_phases_1_3.sh`, and `jetson_edge_smoke_csi.sh` (Option A) instead of duplicating long blocks here.

---

## Notes

- **`$USER` inside double-quoted paths** (Option B only): the shell expands it; do not type your username over `$USER`.
- **CUDA “driver too old”** with pip `torch+cu*`: CPU training still works; reduce `YOLO_BATCH` / `YOLO_EPOCHS` via env when calling `jetson_yolo_train.sh`.
- **Stray `class_map.json` in repo root**: use `models/class_map.json` only.
