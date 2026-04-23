# 3. Detection and tracking

## Goal

Verify ONNX detection and multi-track stability.

**Order:** start **`edge.main`** (§3) with model + class map + calibration, **then** confirm MJPEG and `/health` in the browser. From **Detection and tracking** onward, the setup sidebar can show health lamps for the API and MJPEG port. You do **not** start `edge.main` in **§1** or before `calibration.json` exists.

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
you must create one before running this step (see `edge.main` in §3 below). This is a bootstrap path to get a
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

Add **`--show-track-debug-overlay`** to draw **ball / player / stick / rack** track boxes and IDs on the MJPEG stream (detector frame count + raw detection count in the bottom line). **Off by default** so normal play is uncluttered; use only while debugging detection and ID stability.

**Then test (after models load; first response can take 30–90+ s):** in a browser, open `http://127.0.0.1:8001/mjpeg` and `http://127.0.0.1:8001/health` (or the port you passed to `--mjpeg-port`). The setup guide **Detection and tracking** step uses the same order: run this command, **then** use its overlay / health buttons (MJPEG field must match the port you chose).

`edge.main` does **not** open a desktop window; video is over HTTP.

**macOS (Apple Silicon):** defaults use **USB** (`--camera usb`); there is no Jetson CSI. Grant **Camera** under **System Settings → Privacy & Security → Camera** for the app that runs the shell (Terminal, iTerm, or Cursor). If the wrong webcam is selected, try a different `--usb-index`. An ONNXRuntime message that **CUDAExecutionProvider** is unavailable is normal; CoreML or CPU is used.

**MJPEG port already in use** (`OSError: [Errno 48] Address already in use` or similar in the terminal): another process is still bound to that port—commonly a **stale `python -m edge.main`**, or another script (`phase1.sh`, `phase2.sh`, `jetson_csi_setup.sh`, Docker edge, etc.) that started `edge.main` in the background.

**“The overlay works but I didn’t start edge in *this* terminal.”** The setup guide and the browser **do not** launch `edge.main`; they only open URLs. Something else is still listening (often an **older** terminal session, a **minimized** window, a **Cursor** task, a **manual** `edge.main` you forgot, or **Docker** edge). The browser does not *host* MJPEG—it only connects to whatever is already bound to the port.

**Does this repo detach `edge.main` on purpose?** `scripts/phase1.sh` and `phase2.sh` may start `edge.main` in the background (`&`) and **`kill` it** when each step finishes, with a shell **`trap` on `EXIT`**. `phase1.sh` / `phase2.sh` may use `timeout`/`gtimeout` around `edge` on some systems — a known sharp edge (wrapper PID vs Python PID) if not cleaned up. Phases do **not** use `nohup` or `disown` for edge. If a run is ended with **`kill -9`**, the trap may not run and a stray `edge.main` is possible. The backend’s **`POST /api/setup/launch`** uses `subprocess` with `start_new_session=True` only for **`start_calibration.sh`**, not for `edge.main`. The setup app does not start MJPEG; only `edge.main` (or another process you start) does.

1. See what is listening: `lsof -nP -iTCP:8001 -sTCP:LISTEN` (macOS/Linux). Then: `ps -p <pid> -o args=` (use your `--mjpeg-port` if not 8001).
2. Stop that process (`kill <pid>`) or stop the Docker stack. Closing browser tabs alone does not stop the server.
3. If you use the Setup guide overlay, set the sidebar **MJPEG** field to the same port as your `edge.main` run.

## 4) Optional manual single-run command (Jetson / CSI)

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

