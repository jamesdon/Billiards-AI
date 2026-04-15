# Jetson Nano deployment

## Baseline target

- JetPack 4.x (Nano) or JetPack 5.x (if supported by your image)
- Python 3.8+ recommended (match JetPack constraints)

## OS prerequisites (Debian/Ubuntu-based Jetson images)

Install venv and pip system packages before creating a virtual environment:

```bash
# If apt update fails on third-party repos (for example gh-cli key issues),
# you can still install camera prerequisites from Ubuntu/NVIDIA repos:
sudo /usr/bin/apt-get update || true
sudo /usr/bin/apt-get install -y python3-venv python3-pip
```

If `python3 -m venv` still reports `ensurepip is not available`, install the
version-specific venv package that matches `/usr/bin/python3 --version`
(example shown for Python 3.10):

```bash
sudo /usr/bin/apt-get install -y python3.10-venv
```

## Install

From repo root:

```bash
cd "/home/$USER/Billiards-AI"
/usr/bin/rm -rf "/home/$USER/Billiards-AI/.venv"
/usr/bin/python3 -m venv --system-site-packages "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
# Prevent Python from loading user-site packages like ~/.local/lib/pythonX.Y/site-packages
# that can shadow Jetson system OpenCV with a non-GStreamer build.
export PYTHONNOUSERSITE=1
/usr/bin/python3 -m pip install -U pip wheel
# IMPORTANT: install Jetson-compatible numeric stack first.
python -m pip install "numpy<2"
# IMPORTANT: prevent pip from pulling opencv-python wheel on Jetson.
python -m pip install --no-cache-dir --upgrade --ignore-installed --no-deps -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip install --no-cache-dir --upgrade --ignore-installed onnxruntime fastapi uvicorn pydantic orjson pytest pytest-timeout ruff boto3
# Quick verification: "GStreamer: YES" is required for --camera csi
python - <<'PY'
import cv2
print("cv2:", cv2.__file__)
print("GStreamer:", "YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "NO")
PY
```

If `cv2` path points to `/home/$USER/.local/...`, remove user-site OpenCV packages
or run with `PYTHONNOUSERSITE=1`.

Example cleanup for user-site shadow packages:

```bash
/usr/bin/python3 -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless
/usr/bin/rm -rf "/home/$USER/.local/lib/python3.10/site-packages/cv2"*
```

If this reports `GStreamer: NO`, remove pip OpenCV and use distro OpenCV:

```bash
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless
sudo /usr/bin/apt-get install -y python3-opencv python3-gst-1.0 gstreamer1.0-tools
# reinstall non-OpenCV Python deps only
python -m pip install --no-cache-dir --upgrade --ignore-installed "numpy<2" onnxruntime fastapi uvicorn pydantic orjson pytest pytest-timeout ruff boto3
```

Expected check output after fix:

- `cv2_path` should point to `/usr/lib/python3/dist-packages/...`
- `GStreamer:                   YES`

If `cv2` import fails with `_ARRAY_API not found` or `numpy.core.multiarray failed to import`,
your environment has a NumPy ABI mismatch (NumPy 2.x with OpenCV built against NumPy 1.x).
Fix by pinning NumPy below 2:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install --force-reinstall "numpy<2"
```

## Model optimization

See `docs/MODEL_OPTIMIZATION.md` for ONNX/TensorRT steps.

## Run edge pipeline (CSI camera required)

```bash
cd "/home/$USER/Billiards-AI"
source .venv/bin/activate
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --calib "./calibration.json" --mjpeg-port 8080
```

`--csi-flip-method` is passed directly to Jetson `nvvidconv`:

- `0`: no flip
- `6`: vertical flip (typical "camera mounted upside down" fix)
- `2`: 180 degree rotate (if both vertical and horizontal appear inverted)

## CSI troubleshooting (Jetson)

If startup fails with `RuntimeError: Failed to open camera source=...`, validate
the Jetson camera stack before retrying the app:

```bash
cd "/home/$USER/Billiards-AI"
chmod +x "/home/$USER/Billiards-AI/scripts/jetson_csi_setup.sh"
"/home/$USER/Billiards-AI/scripts/jetson_csi_setup.sh"
```

Manual checks:

```bash
sudo /usr/bin/systemctl restart nvargus-daemon
/usr/bin/timeout 10 /usr/bin/gst-launch-1.0 -e nvarguscamerasrc sensor-id=0 ! "video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1" ! nvvidconv ! "video/x-raw,format=I420" ! fakesink
```

## Docker-first deployment (recommended)

```bash
cd "/home/$USER/Billiards-AI"
chmod +x scripts/docker_jetson_build.sh scripts/docker_jetson_up.sh scripts/docker_jetson_down.sh
scripts/docker_jetson_build.sh
scripts/docker_jetson_up.sh
```

Notes:

- Place detector assets in `/home/$USER/Billiards-AI/models/` (`model.onnx` + `class_map.json`; same paths in Docker via `./models` → `/models`)
- Place calibration and identities in `/home/$USER/Billiards-AI/data/`
- CSI camera is default in container command (`--camera csi`)

## systemd (optional)

Create a service that runs `edge.main` on boot, binds to MJPEG port, and logs to journald.

