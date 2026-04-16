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

## Docker on Jetson (recommended)

Use the Jetson compose stack to minimize dependency drift:

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

