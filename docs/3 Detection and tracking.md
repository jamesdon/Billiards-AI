# 3. Detection and tracking

## Goal

Verify ONNX detection and multi-track stability.

**Order:** start **`edge.main`** (§3) with model + class map + calibration, **then** confirm MJPEG and `/health` in the browser. **Optionally** run **`scripts/phase3.sh`** (§4) for a full sweep. From **Detection and tracking** onward, the setup sidebar can show a short **edge** line. You do **not** start `edge.main` in **§1** or before `calibration.json` exists.

**Prerequisite note:** This section assumes `models/model.onnx` and `models/class_map.json` are already on the device. **Training that model is a separate, optional step** (see `docs/MODEL_OPTIMIZATION.md`); day-to-day new installs typically **reuse the same exported model** and only run calibration plus this detection/tracking smoke.

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
you must create one before running this step (`scripts/phase3.sh` or `edge.main`). This is a bootstrap path to get a
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

## 3) Start `edge.main` manually (do this first; then test MJPEG/health)

From the **repository root**, venv active, default: **macOS** + **USB** index 0. Adjust paths if your clone or files live elsewhere. **Jetson (CSI):** use `--camera csi` and omit `--usb-index` (see §5 for a longer CSI example).

```bash
cd "/Users/jdonn/AppDev/Billiards-AI"
source "/Users/jdonn/AppDev/Billiards-AI/.venv/bin/activate"
python3 -m edge.main \
  --camera usb \
  --usb-index 0 \
  --onnx-model "/Users/jdonn/AppDev/Billiards-AI/models/model.onnx" \
  --class-map "/Users/jdonn/AppDev/Billiards-AI/models/class_map.json" \
  --calib "/Users/jdonn/AppDev/Billiards-AI/calibration.json" \
  --mjpeg-port 8001
```

**Then test (after models load; first response can take 30–90+ s):** in a browser, open `http://127.0.0.1:8001/mjpeg` and `http://127.0.0.1:8001/health` (or the port you passed to `--mjpeg-port`). The setup guide **Detection and tracking** step uses the same order: run this command, **then** use its overlay / health buttons (MJPEG field must match the port you chose).

`edge.main` does **not** open a desktop window; video is over HTTP. Grant **Camera** to your terminal on macOS if prompted.

## 4) Run the verification script (`scripts/phase3.sh`) (full sweep, recommended after §3)

**Before `phase3.sh`:** the script **starts and stops** its own `edge.main` on the sweep ports (defaults **8001**, **8004**, **8005**). If you still have a **manual** `edge.main` running from §3 (e.g. `curl http://127.0.0.1:8001/health` works), that process holds **8001** and the script will fail with **Address already in use** unless you **stop** that `edge` first, or set **`PHASE3_PORT_N2` / `PHASE3_PORT_N1` / `PHASE3_PORT_N3`** to three **free** ports in **8001–8005**.

This script performs:

- baseline run at `--detect-every-n 2`
- sweep runs at `--detect-every-n 1` and `--detect-every-n 3`
- MJPEG readiness checks for each run
- per-run logs under repo root: `.phase3_n1.log`, `.phase3_n2.log`, `.phase3_n3.log`

**Startup can look “hung”:** After each `[Phase3] Starting …` line the script waits for the first good `/mjpeg` response with **no** OpenCV window. On a cold Mac that often takes **30–90+ seconds** (ONNX + camera). In another terminal, tail the per-run log at the **repo root** (paths are on one line; adjust to your clone):

```bash
tail -f "/Users/jdonn/AppDev/Billiards-AI/.phase3_n2.log"
```

The **Setup guide** (when the backend is running: open **Detection and tracking** in the wizard) shows the same `tail` command with your real clone path and a one-click **Copy** next to it. You can also wait for **`[Phase3] Live MJPEG`**. The wait is capped by **`PHASE3_MJPEG_WAIT_SECONDS`** (default **90**).

**Viewing video:** This step does **not** open a desktop window. `edge.main` serves an MJPEG stream over HTTP. When the script prints `Live MJPEG`, open the printed URL. The script uses fixed sweep ports **8001** (baseline, `detect_every_n=2`), **8004** (`detect_every_n=1`), and **8005** (`detect_every_n=3`). See **`docs/PORTS.md`**. Override with **`PHASE3_PORT_N2`**, **`PHASE3_PORT_N1`**, **`PHASE3_PORT_N3`** (each **8001–8005**; not **8000**, API). **`/health`** on each run’s port reports JSON status.

**MJPEG port already in use** (`OSError: [Errno 48] Address already in use` or `MJPEG port 8001 is already in use` in `.phase3_n2.log`): another process is still bound to that port—commonly a **stale `python -m edge.main`**, a **browser tab** or **Setup guide** still loading `http://127.0.0.1:8001/mjpeg`, or a second `scripts/phase3.sh` run.

1. See what is listening: `lsof -nP -iTCP:8001 -sTCP:LISTEN` (macOS/Linux).
2. Stop that process (e.g. `kill <pid>`) or close tabs/apps using the stream, then re-run the script.
3. Or point the **baseline** at another free port in **8001–8005**, e.g. `PHASE3_PORT_N2=8002` when invoking `scripts/phase3.sh`. If you use the Setup guide overlay buttons, set the **MJPEG** field in the sidebar to the same port as your edge run.

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
MODEL_PATH="/ABSOLUTE/PATH/TO/model.onnx" \
CLASS_MAP_PATH="/home/$USER/Billiards-AI/models/class_map.json" \
PHASE3_CAMERA=csi \
CSI_SENSOR_ID=0 \
CSI_FLIP_METHOD=6 \
EDGE_TIMEOUT_SECONDS=1200 \
"/home/$USER/Billiards-AI/scripts/phase3.sh"
```

**macOS (Apple Silicon):** `scripts/phase3.sh` defaults to **`PHASE3_CAMERA=usb`** (there is no Jetson CSI). Grant **Camera** permission to the app that runs the shell (Terminal, iTerm, or Cursor) under **System Settings → Privacy & Security → Camera**. If the wrong webcam is selected, try **`PHASE3_USB_INDEX=1`**. An ONNXRuntime message that **CUDAExecutionProvider** is unavailable is normal; CoreML or CPU is used instead. The phase script uses **`timeout`** when available; stock macOS has no `/usr/bin/timeout`, so the helper falls back to **`gtimeout`** (Homebrew `coreutils`) or runs **without** a wall-clock cap—either is fine for local smoke tests. Scripts call **`sleep`** from your `PATH` (not `/usr/bin/sleep`), which avoids hosts where that path is missing.

## 5) Optional manual single-run command (Jetson / CSI)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 "$(pwd)/.venv/bin/python3" -m edge.main \
  --camera csi \
  --csi-sensor-id 0 \
  --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" \
  --class-map "/home/$USER/Billiards-AI/models/class_map.json" \
  --detect-every-n 2 \
  --mjpeg-port 8001
```

On macOS for a manual run, use `--camera usb` (and `--usb-index` if needed) instead of `csi`.

## Tuning notes (tracker, shot detector, detector cadence)

- **`IoUTracker`**: associations use IoU against a **constant-velocity predicted bbox** (px/s). If IoU is still weak right after a large jump (no velocity estimate yet), a **center-distance fallback** (`center_match_max_dist_px` on `IoUTrackerConfig`) can still lock the same track ID.
- **`ShotDetector`**: shot start uses **true** cue-ball acceleration, **|Δv| / Δt** in **m/s²** (not a unitless per-frame Δv). Default `cue_accel_thres` is tuned for ~30 FPS-style timing; retune if your clocking or `detect_every_n` differs.
- **`detect_every_n`**: the detector may run every N frames while the pipeline still steps every frame. Ball **positions and finite-difference velocities** therefore update on detection frames; kinematic detectors (shot, collision, rail) still run every frame and can see **stale** velocities for up to N−1 frames. See `EdgePipelineConfig` docstring in `edge/pipeline.py`.

## Pass criteria

- no detector/tracker crashes
- IDs remain stable for moving balls/players/sticks in normal play
- manual `edge.main` (§3) serves MJPEG and `/health` on the chosen port
- optional: `scripts/phase3.sh` (§4) — sweep logs exist for `n=1,2,3` and each run reaches MJPEG endpoint

