# Jetson Nano: train YOLO on-device, then run tests (Billiards-AI)

## Copy-paste usage (read once)

Use **bash** on the Jetson (desktop terminal or SSH). Each block below is one **copy-paste** unit: select the whole fenced block, paste, Enter.

**`$USER` is a normal environment variable** (your login name). These commands use **double quotes** so the shell expands `/home/$USER/...` when the line runs. **You do not type your username instead of `$USER`**—leave it exactly as shown.

Do **not** paste into `sh` or `fish` unless you know how to translate; use `bash`.

---

## Paths (reference only)

| Wrong | Correct in bash (paste as-is) |
|-------|----------------------------------|
| macOS paths under `/Users/...` | `"/home/$USER/Billiards-AI/..."` |
| A `billiards-data.yaml` whose `path:` line literally contains the characters `$USER` | Run the bootstrap block below; it writes a real absolute path. |

---

## Block 1 — Repo, venv, training dependencies

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

If NumPy/matplotlib was broken earlier, run Block 1 again (same paste).

Torch: if `python -c "import torch"` fails, install Jetson PyTorch from NVIDIA for your JetPack, then run the two `pip install -r ...` lines again.

CUDA “driver too old” with pip `torch+cu*`: training falls back to **CPU** until you use a Jetson-built wheel—that is OK for small runs. Prefer `batch=4`, `workers=2` or lower on Nano.

---

## Block 2 — Dataset directories and `billiards-data.yaml` (required before `yolo train`)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
chmod +x "/home/$USER/Billiards-AI/scripts/bootstrap_billiards_dataset.sh"
PROJECT_ROOT="/home/$USER/Billiards-AI" "/home/$USER/Billiards-AI/scripts/bootstrap_billiards_dataset.sh"
/usr/bin/grep '^path:' "/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml"
```

The `grep` line must print **one** `path:` line whose value is `/home/` + your username + `/Billiards-AI/data/datasets/billiards`. It must **not** show the four characters `$` `U` `S` `E` `R` inside that file.

Then add your images and YOLO `.txt` labels under `data/datasets/billiards/images/{train,val}` and `data/datasets/billiards/labels/{train,val}` (class ids `0`–`3` matching `models/class_map.json`). You need samples in **both** train and val before training.

---

## Block 3 — Train (Jetson-friendly)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
yolo detect train \
  data="/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml" \
  model="/home/$USER/Billiards-AI/yolov8n.pt" \
  imgsz=640 \
  epochs=30 \
  batch=4 \
  workers=2 \
  project="/home/$USER/Billiards-AI/runs/detect"
```

---

## Block 4 — Export latest run to `models/model.onnx` (no manual `train3` name)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
LATEST_PT="$(ls -t "/home/$USER/Billiards-AI/runs/detect/"*/weights/best.pt 2>/dev/null | head -1)"
if [[ -z "${LATEST_PT}" ]]; then echo "No runs found under runs/detect/*/weights/best.pt — run Block 3 first."; exit 1; fi
echo "Using: ${LATEST_PT}"
yolo export model="${LATEST_PT}" format=onnx imgsz=640
WEIGHTS_DIR="$(dirname "${LATEST_PT}")"
ONNX_OUT="${WEIGHTS_DIR}/best.onnx"
if [[ ! -f "${ONNX_OUT}" ]]; then echo "Missing ${ONNX_OUT} after export"; exit 1; fi
mkdir -p "/home/$USER/Billiards-AI/models"
cp "${ONNX_OUT}" "/home/$USER/Billiards-AI/models/model.onnx"
ls -lh "/home/$USER/Billiards-AI/models/model.onnx" "/home/$USER/Billiards-AI/models/class_map.json"
```

---

## Block 5 — Pytest

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m pytest "/home/$USER/Billiards-AI/tests" -q --tb=short
```

---

## Block 6 — Phase scripts (env + examples)

```bash
export PROJECT_ROOT="/home/$USER/Billiards-AI"
export MODEL_PATH="/home/$USER/Billiards-AI/models/model.onnx"
export CLASS_MAP_PATH="/home/$USER/Billiards-AI/models/class_map.json"
"/home/$USER/Billiards-AI/scripts/run_phase.sh" 1
"/home/$USER/Billiards-AI/scripts/run_phase.sh" 3
```

---

## Block 7 — Edge smoke (CSI)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m edge.main \
  --camera csi \
  --csi-sensor-id 0 \
  --onnx-model "/home/$USER/Billiards-AI/models/model.onnx" \
  --class-map "/home/$USER/Billiards-AI/models/class_map.json" \
  --calib "/home/$USER/Billiards-AI/calibration.json" \
  --detect-every-n 2 \
  --mjpeg-port 8080
```

`--calib` should match where calibration was saved (often `"/home/$USER/Billiards-AI/calibration.json"` from `scripts/start_calibration.sh`).

---

## Optional: stray `class_map.json` in repo root

Prefer `models/class_map.json` only. If an old file exists at `"/home/$USER/Billiards-AI/class_map.json"`, remove it after you no longer need it.
