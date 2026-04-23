# Billiards-AI (edge-first)

Real-time billiards perception + rules engine designed for **NVIDIA Jetson Orin Nano** edge hardware (JetPack 5.x) with optional backend offload.

## Quickstart (dev)

```bash
cd "/home/$USER/Billiards-AI"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 -m edge.main --help
```

**Jetson / aarch64 (including Orin Nano):** `requirements.txt` intentionally **does not** install `opencv-python` from PyPI on `aarch64`/`arm64` (those wheels usually lack GStreamer, which CSI needs). Use **distro** OpenCV and a venv that can see it:

```bash
cd "/home/$USER/Billiards-AI"
sudo /usr/bin/apt-get update
sudo /usr/bin/apt-get install -y python3-venv python3-pip python3-opencv python3-gst-1.0 gstreamer1.0-tools
/usr/bin/rm -rf "/home/$USER/Billiards-AI/.venv"
/usr/bin/python3 -m venv --system-site-packages "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 -c "import cv2; print(cv2.__file__); print('GStreamer:', 'YES' if 'GStreamer:                   YES' in cv2.getBuildInformation() else 'NO')"
```

If `import cv2` still fails, see **`docs/DEPLOYMENT_JETSON.md`** and **`docs/1 Environment and startup.md`** (NumPy `<2`, user-site shadows, and optional `--no-deps` installs).

**Repair when checks show pip OpenCV (`…/.venv/…/cv2`) or `GStreamer: NO`:** you must stop using the PyPI `opencv-python` wheel in this venv (Ultralytics / `requirements-train.txt` installs it) and use distro OpenCV instead. Run **all** of:

```bash
cd "/home/$USER/Billiards-AI"
# 1) Remove this venv (discards pip opencv-python and other venv-only packages).
/usr/bin/rm -rf "/home/$USER/Billiards-AI/.venv"
# 2) Stop user-site OpenCV from shadowing distro cv2 in any future venv.
export PYTHONNOUSERSITE=1
/usr/bin/python3 -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true
for _cv in "/home/$USER"/.local/lib/python3.*/site-packages/cv2*; do [ -e "$_cv" ] && /usr/bin/rm -rf "$_cv"; done
# 3) Distro OpenCV + GStreamer (versions match your Jetson image).
sudo /usr/bin/apt-get update
sudo /usr/bin/apt-get install -y python3-venv python3-pip python3-opencv python3-gst-1.0 gstreamer1.0-tools
# 4) New venv that can import apt’s cv2.
/usr/bin/python3 -m venv --system-site-packages "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python3 -m pip install -U pip wheel
python3 -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python3 -m pip install --upgrade "numpy<2"
# 5) Verify: path must be under /usr/lib/.../dist-packages, GStreamer must be YES.
python3 -c "import cv2; print(cv2.__file__); print('GStreamer:', 'YES' if 'GStreamer:                   YES' in cv2.getBuildInformation() else 'NO')"
```

Do **not** run `pip install -r requirements-train.txt` in this venv if you need CSI; it will pull `opencv-python` again. Use a **second** venv (or another machine) for Ultralytics training.

**Fixed local ports (defaults):** see **`docs/PORTS.md`** (API **8000**, MJPEG **8001**–**8005**).

## Guided setup (browser) — start here

The **setup guide** is the first-run UI: **`GET /setup`** in the FastAPI app (per-step **traffic-light** status, checklists, **Copy** on shell one-liners, in-browser Markdown for `docs/…` via `/api/setup/doc?path=…`, optional **Quick links** and **Launch** when enabled). The left sidebar has **red/green health lamps** next to the **API** line (`GET /health`), the **Port …: edge** line (server-side `GET /api/setup/edge-health?port=…` probing `http://127.0.0.1:<port>/health` for `edge.main`), and the **Stream** line (same probe as edge), plus **project root**, **text size**, and **MJPEG port** (8001–8005), polled about every 10s.

**1. Start the API (this serves the guide):** from the repo root, with the venv you use for this repo:

```bash
./scripts/run_backend.sh
```

This runs **`.venv/bin/python3 -m uvicorn backend.app:app`** (avoids a broken **`.venv/bin/uvicorn`** shim after renames / moves). `BACKEND_HOST` and **`BACKEND_PORT`** default to **127.0.0.1** and **8000**; if the port is **already in use** and `http://127.0.0.1:8000/health` works, the API is already up — do **not** start a second copy. **This process does not start edge or MJPEG**; use another terminal and `edge.main` for the camera stream (see the guide and `docs/PORTS.md`).

**2. Open the guide:** **[http://127.0.0.1:8000/setup](http://127.0.0.1:8000/setup)** (use your `BACKEND_PORT` if you changed it: `http://127.0.0.1:<port>/setup`).

**3. How it lines up with the repo:** sidebar step names match the table at the top of **`docs/TEST_PLAN.md`** (and the numbered runbooks **`docs/1` … `docs/9`** where those apply). Gates and execution order are in that file.

**4. Where progress is stored:** `data/setup_wizard_progress.json` and browser **localStorage** (saved when you use **Save** or leave the page; same keys as step `id` in `backend/setup_guide.py`).

**5. Optional — launch scripts from the UI:** set **`SETUP_ALLOW_LAUNCH=1`** and bind only to localhost, then restart the API; the Calibration step can start **`scripts/start_calibration.sh`** from the page.

**6. Direct uvicorn (alternative to the script):** with venv active, `python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000` (still prefer **`./scripts/run_backend.sh`** so port-in-use and shim issues are handled consistently).

## Jetson-family edge assumptions

- **Target platform**: NVIDIA Jetson **Orin Nano** (JetPack **5.x**; Ampere GPU). Older Jetson Nano + JetPack 4.x notes are legacy; behavior differs (Python versions, CUDA arch, wheel availability).
- **Project path**: expected at `"/home/$USER/Billiards-AI"` on device.
- **Camera source**:
  - CSI camera is the default: `--camera csi`
  - CSI camera is the required production/test path for this project
  - optional CSI controls: `--csi-sensor-id`, `--csi-framerate`, `--csi-flip-method`
  - setup helper script: `scripts/jetson_csi_setup.sh`
- **Acceleration**:
  - ONNXRuntime is baseline runtime.
  - TensorRT/FP16 optimization is the preferred production path on Orin-class Jetson (see `docs/MODEL_OPTIMIZATION.md`).
- **No Raspberry Pi target**:
  - scripts and docs in this repo are authored for Jetson/Linux conventions only.

## Docker on L4T / Orin Nano (recommended)

Use the Jetson-family compose stack to minimize dependency drift:

```bash
cd "/home/$USER/Billiards-AI"
chmod +x scripts/docker_jetson_build.sh scripts/docker_jetson_up.sh scripts/docker_jetson_down.sh
scripts/docker_jetson_build.sh
scripts/docker_jetson_up.sh
```

Required runtime assets:

- Detector bundle (single directory `models/`): `model.onnx` + `class_map.json` with matching class indices (`MODEL_PATH` / `CLASS_MAP_PATH` override defaults; Docker mounts `./models` → `/models`)
- `/home/$USER/Billiards-AI/data/calibration.json` (per table / per camera install)

The repo ships **`models/class_map.json`** as the canonical label map. **`models/model.onnx`** is the exported detector: **track it in git** after training (see `docs/MODEL_OPTIMIZATION.md`). Typical flow on a trainer: `bash scripts/jetson_yolo_train_export_publish.sh`, or export then `bash scripts/publish_trained_model.sh` (set **`GIT_PUSH=1`** to push). Other machines **`git pull`** and run—no manual `scp` of weights. If the ONNX exceeds GitHub’s size guidance (~50–100MB), use **Git LFS** for `models/model.onnx` (documented in `docs/MODEL_OPTIMIZATION.md`).

Stop:

```bash
cd "/home/$USER/Billiards-AI"
scripts/docker_jetson_down.sh
```

## Docs

- **`docs/TEST_PLAN.md`** — §1–§9 delivery sections, pass/fail gates, and a **table** of setup guide step titles vs this file and `docs/1`–`docs/9`
- `docs/PORTS.md` — default **8000** (API / setup) vs **8001–8005** (MJPEG / edge)
- `docs/FILE_HIERARCHY.md` — tree of components (includes `backend/setup_guide.py` and `static/setup/`)
- `docs/ARCHITECTURE.md`
- `docs/MODEL_OPTIMIZATION.md` (optional train/tune; normal deploy reuses ONNX)
- `docs/ORIN_NANO_TRAIN_AND_TEST.md` (train + pytest + `run_phase` / smoke scripts **on the Orin Nano**; `/home/$USER/Billiards-AI` paths; legacy alias `docs/JETSON_NANO_TRAIN_AND_TEST.md`)
- `docs/CALIBRATION.md`
- `docs/EVENT_DETECTION.md`
- `docs/RULES_ENGINE.md`
- `docs/DEPLOYMENT_JETSON.md`

