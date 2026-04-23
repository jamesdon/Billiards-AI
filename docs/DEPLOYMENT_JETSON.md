# Jetson Orin Nano deployment

## Baseline target

- **Hardware:** NVIDIA Jetson Orin Nano (Ampere GPU; Jetson Nano / Maxwell is **not** the reference board for this repo).
- **OS stack:** JetPack **5.x** (L4T based on Ubuntu 20.04 or 22.04 depending on image).
- **Python:** 3.8–3.10 typical on JetPack 5; **3.10** is common on newer images—match your venv to `/usr/bin/python3`.

Orin Nano vs older Jetson Nano (JetPack 4.x): more headroom for ONNX Runtime and TensorRT, a more mature GStreamer CSI path, and generally fewer wheel surprises—but **distro OpenCV + pip NumPy 2.x** can still break imports. This doc keeps **`numpy<2`** when mixing pip packages with `python3-opencv` until you have verified a clean stack.

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

## Install (edge venv)

From repo root, use the single installer (replaces manual copy-paste blocks):

```bash
cd "/home/$USER/Billiards-AI"
chmod +x scripts/setup_jetson_edge_venv.sh
bash scripts/setup_jetson_edge_venv.sh
```

If OpenCV is wrong (**`GStreamer: NO`**, pip **`cv2`** under **`.venv/site-packages`**, or NumPy ABI errors), run **`bash scripts/setup_jetson_edge_venv.sh`** again from the repo root. More detail: **`docs/1 Environment and startup.md`**.

## Model optimization

See `docs/MODEL_OPTIMIZATION.md` for ONNX/TensorRT steps.

## Run edge pipeline (CSI camera required)

```bash
cd "/home/$USER/Billiards-AI"
source .venv/bin/activate
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --calib "./calibration.json" --mjpeg-port 8001
```

`--csi-flip-method` is passed through the GStreamer pipeline to **`nvvidconv`** `flip-method` on Jetson:

- `0`: no flip
- `6`: vertical flip (typical "camera mounted upside down" fix)
- `2`: 180 degree rotate (if both vertical and horizontal appear inverted)

## CSI troubleshooting (Jetson / Argus)

If startup fails with `RuntimeError: Failed to open camera source=...`, validate
the camera stack before retrying the app:

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

- Detector assets live under `/home/$USER/Billiards-AI/models/` (`model.onnx` + `class_map.json`; same paths in Docker via `./models` → `/models`). **`model.onnx` is intended to live in git** on your team branch—bring the device up with **`git pull`**, then see `scripts/publish_trained_model.sh` / `docs/MODEL_OPTIMIZATION.md` when refreshing weights.
- Place calibration JSON in `/home/$USER/Billiards-AI/data/` (or your chosen `CALIB_PATH`)
- Player/stick profiles live at **`<repo>/identities.json`** (bind-mounted into containers as `/app/identities.json`; create the file before first `docker compose` if missing, e.g. `echo '{\"players\":[],\"sticks\":[]}' > identities.json`)
- CSI camera is default in container command (`--camera csi`)

## systemd (optional)

Create a service that runs `edge.main` on boot, binds to MJPEG port, and logs to journald.
