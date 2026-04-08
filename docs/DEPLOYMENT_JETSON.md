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
/usr/bin/python3 -m venv "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -U pip wheel
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
```

## Model optimization

See `docs/MODEL_OPTIMIZATION.md` for ONNX/TensorRT steps.

## Run edge pipeline (USB cam example)

```bash
cd "/home/$USER/Billiards-AI"
source .venv/bin/activate
python -m edge.main --camera 0 --calib "./calibration.json" --mjpeg-port 8080
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

