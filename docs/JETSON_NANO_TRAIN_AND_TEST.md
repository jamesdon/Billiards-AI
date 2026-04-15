# Jetson Nano: train YOLO on-device, then run tests (Billiards-AI)

This guide assumes **everything happens on the Jetson** at:

`/home/$USER/Billiards-AI`

Same path convention as Phase 2 (`docs/Phase 2 Calibration and coordinate mapping.md`). Replace `$USER` with your Linux username if you copy paths outside a shell.

## Paths you must use on the Jetson

| Wrong (Mac / copy-paste hazard) | Correct on the Jetson |
|---------------------------------|------------------------|
| `/Users/.../Billiards-AI/...` | `/home/$USER/Billiards-AI/...` |
| YAML `path:` containing the literal characters `$USER` (from a quoted heredoc) | Real absolute path; use `scripts/bootstrap_billiards_dataset.sh` or an **unquoted** heredoc so the shell expands `$USER` when creating the file |

Use **only** absolute paths under `/home/$USER/Billiards-AI` for `data=`, `--onnx-model`, `--class-map`, and calibration.

## 1) One-time: repo, venv, training dependencies

```bash
cd "/home/$USER/Billiards-AI"
git pull
```

Create or refresh the venv (Jetson uses `--system-site-packages` for GStreamer OpenCV; `scripts/common.sh` handles this when invoked from other scripts):

```bash
cd "/home/$USER/Billiards-AI"
test -d .venv || python3 -m venv --system-site-packages .venv
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip install -r "/home/$USER/Billiards-AI/requirements-train.txt"
```

`requirements-train.txt` pins **`numpy<2`** and installs **`matplotlib` into the venv** so Ultralytics does not import the broken combo of **venv NumPy 2.x + Ubuntu’s system matplotlib** (the `_ARRAY_API` / `multiarray` errors).

If you already ran `pip install -U ultralytics` alone and broke NumPy, repair:

```bash
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip install -r "/home/$USER/Billiards-AI/requirements-train.txt"
```

Optional but recommended for reproducibility (matches phase scripts and avoids `~/.local` shadowing):

```bash
export PYTHONNOUSERSITE=1
```

If after that `python -c "import torch"` fails, install a Jetson-compatible **torch** inside the venv from NVIDIA’s Jetson PyTorch instructions for your JetPack version, then reinstall `requirements-train.txt`.

## 2) CUDA warning and CPU training on Nano

If you see **CUDA initialization: The NVIDIA driver on your system is too old** while `torch` is a generic **pip CUDA** build (e.g. `+cu130`), PyTorch will fall back to **CPU**. That is normal until you install a **Jetson-built** torch wheel that matches your JetPack driver.

Training on **CPU** works but is slow; use small epochs and a small dataset first:

- `batch=2` or `batch=4`
- `workers=0` or `workers=2`

## 3) Dataset layout and YAML (must exist before `yolo train`)

The file `data/datasets/billiards/billiards-data.yaml` is **not** committed (it must contain a real absolute `path:`). After `git pull`, create it with:

```bash
cd "/home/$USER/Billiards-AI"
chmod +x "/home/$USER/Billiards-AI/scripts/bootstrap_billiards_dataset.sh"
PROJECT_ROOT="/home/$USER/Billiards-AI" "/home/$USER/Billiards-AI/scripts/bootstrap_billiards_dataset.sh"
/usr/bin/grep '^path:' "/home/$USER/Billiards-AI/data/datasets/billiards/billiards-data.yaml"
```

You must see one line of the form:

`path: /home/<your-username>/Billiards-AI/data/datasets/billiards`

**not** the four characters `$USER` inside the file.

Add labeled images and YOLO labels:

- Images: `data/datasets/billiards/images/train` and `.../val`
- Labels: `data/datasets/billiards/labels/train` and `.../val` (same basename as each image, `.txt` per image)

Class indices in label files must match `models/class_map.json` (`0` ball … `3` rack). Until you have at least a few images in **both** train and val, Ultralytics may still error; add a minimal pair of images/labels for a smoke train.

## 4) Train (Jetson-friendly command)

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

Adjust `epochs` / `batch` for your patience and RAM. New runs create `train`, `train2`, … under `runs/detect/`; use the latest `weights/best.pt`.

## 5) Export ONNX and install for the edge pipeline

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1

# Replace train3 with your latest run directory name under runs/detect/
yolo export \
  model="/home/$USER/Billiards-AI/runs/detect/train3/weights/best.pt" \
  format=onnx \
  imgsz=640

mkdir -p "/home/$USER/Billiards-AI/models"
cp "/home/$USER/Billiards-AI/runs/detect/train3/weights/best.onnx" "/home/$USER/Billiards-AI/models/model.onnx"
ls -lh "/home/$USER/Billiards-AI/models/model.onnx" "/home/$USER/Billiards-AI/models/class_map.json"
```

`models/class_map.json` is tracked in git and must stay aligned with your YOLO `names` order.

## 6) Run automated tests on the Jetson

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m pytest "/home/$USER/Billiards-AI/tests" -q --tb=short
```

## 7) Phase scripts (camera / model where noted)

```bash
export PROJECT_ROOT="/home/$USER/Billiards-AI"
export MODEL_PATH="/home/$USER/Billiards-AI/models/model.onnx"
export CLASS_MAP_PATH="/home/$USER/Billiards-AI/models/class_map.json"
```

Examples:

```bash
"/home/$USER/Billiards-AI/scripts/run_phase.sh" 1
"/home/$USER/Billiards-AI/scripts/run_phase.sh" 3
```

Phase 3 expects `models/model.onnx` and defaults `CLASS_MAP_PATH` to `models/class_map.json` when unset.

## 8) Quick edge smoke (CSI)

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

Calibration path should match where `start_calibration.sh` wrote JSON (often `/home/$USER/Billiards-AI/calibration.json`).

## 9) Old `class_map.json` in repo root

If `git pull` left you with **only** `models/class_map.json`, use that path. If you still have a stray `/home/$USER/Billiards-AI/class_map.json`, prefer **`models/class_map.json`** for all commands and delete the duplicate when you are confident nothing references it.
