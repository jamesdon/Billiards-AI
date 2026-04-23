# Billiards-AI (edge-first)

Real-time billiards perception + rules engine designed for **NVIDIA Jetson Orin Nano** edge hardware (JetPack 5.x) with optional backend offload.

## Quickstart (dev)

```bash
cd "/home/$USER/Billiards-AI"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m edge.main --help
```

**Guided setup (browser):** from the repo root, run **`./scripts/run_backend.sh`** (uses `.venv/bin/python3 -m uvicorn`, which still works if `.venv/bin/uvicorn` is broken after moving/renaming the project folder). Alternatively: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8780` with the venv active. Open **http://127.0.0.1:8780/setup** for a step-by-step menu: traffic-light status per step, per-line **How to verify** text with backticked shell you can **Copy** into a terminal, **documentation links** that open Markdown in the browser (`/api/setup/doc?path=…`), and links to open files in **VS Code** / **Cursor**. Progress is saved under `data/setup_wizard_progress.json`. Optional: set **`SETUP_ALLOW_LAUNCH=1`** before uvicorn to allow the Calibration step to **start `scripts/start_calibration.sh` from the UI** (localhost only).

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

- `docs/ARCHITECTURE.md`
- `docs/FILE_HIERARCHY.md`
- `docs/MODEL_OPTIMIZATION.md` (optional train/tune; normal deploy reuses ONNX)
- `docs/ORIN_NANO_TRAIN_AND_TEST.md` (train + pytest + phases **on the Orin Nano**; `/home/$USER/Billiards-AI` paths; legacy alias `docs/JETSON_NANO_TRAIN_AND_TEST.md`)
- `docs/CALIBRATION.md`
- `docs/EVENT_DETECTION.md`
- `docs/RULES_ENGINE.md`
- `docs/DEPLOYMENT_JETSON.md`
- `docs/TEST_PLAN.md` (phase gates; includes **live CSI capture** for YOLO dataset build)

