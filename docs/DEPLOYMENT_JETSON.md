# Jetson Nano deployment

## Baseline target

- JetPack 4.x (Nano) or JetPack 5.x (if supported by your image)
- Python 3.8+ recommended (match JetPack constraints)

## OS prerequisites (Debian/Ubuntu-based Jetson images)

Install venv and pip system packages before creating a virtual environment:

```bash
sudo /usr/bin/apt-get update
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
/usr/bin/python3 -m pip install -U pip wheel
# Use Jetson system OpenCV (GStreamer-enabled); avoid pip wheel OpenCV for CSI.
python -m pip install --no-cache-dir --upgrade --ignore-installed -r "/home/$USER/Billiards-AI/requirements.txt"
# Quick verification: "GStreamer: YES" is required for --camera csi
python - <<'PY'
import cv2
print("cv2:", cv2.__file__)
print("GStreamer:", "YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "NO")
PY
```

If this reports `GStreamer: NO`, remove pip OpenCV and use distro OpenCV:

```bash
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless
sudo /usr/bin/apt-get install -y python3-opencv python3-gst-1.0 gstreamer1.0-tools
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
```

## Model optimization

See `docs/MODEL_OPTIMIZATION.md` for ONNX/TensorRT steps.

## Run edge pipeline (CSI camera required)

```bash
cd "/home/$USER/Billiards-AI"
source .venv/bin/activate
python -m edge.main --camera csi --csi-sensor-id 0 --calib "./calibration.json" --mjpeg-port 8080
```

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

- Place model assets in `/home/$USER/Billiards-AI/models/`
- Place calibration and identities in `/home/$USER/Billiards-AI/data/`
- CSI camera is default in container command (`--camera csi`)

## systemd (optional)

Create a service that runs `edge.main` on boot, binds to MJPEG port, and logs to journald.

