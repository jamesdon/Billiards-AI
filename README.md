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

**Fixed local ports (defaults):** see **`docs/PORTS.md`** (API **8000**, MJPEG **8001**–**8005**).

## Guided setup (browser) — start here

The **setup guide** is the first-run UI: **`GET /setup`** in the FastAPI app (per-step **traffic-light** status, checklists, **Copy** on shell one-liners, in-browser Markdown for `docs/…` via `/api/setup/doc?path=…`, optional **Quick links** and **Launch** when enabled). The left sidebar has a fixed **API BACKEND_PORT: default 8000** line, **project root**, **text size**, **MJPEG port** (8001–8005), and (from **Detection and tracking** onward) a short **server-side** `GET /api/setup/edge-health?port=…` line against `http://127.0.0.1:<port>/health` for edge.

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

There is **no bundled `model.onnx`** (weights are gitignored). The repo **does** ship `models/class_map.json` as the canonical label map for training and runtime. **Most new devices only copy** a team-approved `model.onnx` into `models/` beside that file—**training is optional** and done when you create or refresh the shared model. See `docs/MODEL_OPTIMIZATION.md` for the full training walkthrough vs normal deployment.

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

