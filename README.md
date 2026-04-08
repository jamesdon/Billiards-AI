# Billiards-AI (edge-first)

Real-time billiards perception + rules engine designed for constrained edge hardware (Jetson Nano) with optional backend offload.

## Quickstart (dev)

```bash
cd "/home/$USER/Billiards-AI"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m edge.main --help
```

## Jetson-only assumptions

- **Target platform**: NVIDIA Jetson Nano (JetPack 4.x baseline).
- **Project path**: expected at `"/home/$USER/Billiards-AI"` on device.
- **Camera source**:
  - CSI camera is the default: `--camera csi`
  - CSI camera is the required production/test path for this project
  - optional CSI controls: `--csi-sensor-id`, `--csi-framerate`, `--csi-flip-method`
  - setup helper script: `scripts/jetson_csi_setup.sh`
- **Acceleration**:
  - ONNXRuntime is baseline runtime.
  - TensorRT/FP16 optimization is the preferred production path on Jetson (see `docs/MODEL_OPTIMIZATION.md`).
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

- `/home/$USER/Billiards-AI/models/model.onnx`
- `/home/$USER/Billiards-AI/models/class_map.json`
- `/home/$USER/Billiards-AI/data/calibration.json`

Stop:

```bash
cd "/home/$USER/Billiards-AI"
scripts/docker_jetson_down.sh
```

## Docs

- `docs/ARCHITECTURE.md`
- `docs/FILE_HIERARCHY.md`
- `docs/CALIBRATION.md`
- `docs/EVENT_DETECTION.md`
- `docs/RULES_ENGINE.md`
- `docs/DEPLOYMENT_JETSON.md`

