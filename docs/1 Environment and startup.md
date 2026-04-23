# 1. Environment and startup

## Goal

Bring up edge + backend reliably and verify core services.

## 1) Jetson (Linux aarch64 / arm64) — single command

This project targets **Jetson** for CSI. Do **not** use a generic `python3 -m venv` + laptop instructions on the device. Run:

```bash
cd "/home/$USER/Billiards-AI"
chmod +x scripts/setup_jetson_edge_venv.sh
bash scripts/setup_jetson_edge_venv.sh
source "/home/$USER/Billiards-AI/.venv/bin/activate"
.venv/bin/python3 -c "import onnxruntime,cv2; print('imports-ok')"
```

That script installs **`python3-opencv`** from apt, recreates **`.venv`** with **`--system-site-packages`**, installs **`requirements.txt`**, strips pip OpenCV if present, pins **`numpy<2`**, and fails unless **GStreamer** is **YES**.

**Training (Ultralytics)** happens on your **Mac** in a **different** clone/venv with **`requirements-train.txt`**. The Jetson edge venv never installs **`requirements-train.txt`**.

## 2) macOS or Linux x86_64

**macOS:** plain venv, `requirements.txt`, then **`requirements-train.txt`** for YOLO. See **`README.md`** (Mac section). USB camera for edge: **`--camera usb`**.

**Linux x86_64:** plain venv + **`requirements.txt`** only unless you train there. USB or file for camera.

## 3) Quick integrity checks

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 180 python -m compileall "/home/$USER/Billiards-AI/core" "/home/$USER/Billiards-AI/edge" "/home/$USER/Billiards-AI/backend"
/usr/bin/timeout 120 ruff check "/home/$USER/Billiards-AI"
/usr/bin/timeout 300 pytest -q "/home/$USER/Billiards-AI/tests"
```

## 4) Start backend

```bash
cd "/home/$USER/Billiards-AI"
./scripts/run_backend.sh
```

For the **interactive setup guide**, use the same API and open **`http://127.0.0.1:8000/setup`** (see **`README.md`**). Prefer **`scripts/run_backend.sh`** over bare `uvicorn` (stale `.venv/bin/uvicorn` shebang after renames; port-in-use message). Equivalent: venv active, `python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000`.

In another terminal:

```bash
curl -s "http://127.0.0.1:8000/health"
curl -s "http://127.0.0.1:8000/live/state"
```

## 5) Start edge (no model smoke test)

**Jetson CSI:**

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python3 -m edge.main --camera csi --csi-sensor-id 0 --mjpeg-port 8001
```

Vertical flip when the camera is upside down:

```bash
/usr/bin/timeout 1200 python3 -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --mjpeg-port 8001
```

**macOS or Linux x86 (USB):**

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python3 -m edge.main --camera usb --usb-index 0 --mjpeg-port 8001
```

In another terminal:

```bash
curl -s "http://127.0.0.1:8001/mjpeg" >/dev/null
```

## Pass criteria

- backend `/health` returns `{"ok":true}`
- edge process runs without crash for at least 15 minutes
- MJPEG endpoint responds with `200`

## CSI troubleshooting (if camera open fails)

When edge startup fails with `Failed to open camera source='nvarguscamerasrc ...'`, run:

```bash
cd "/home/$USER/Billiards-AI"
chmod +x "/home/$USER/Billiards-AI/scripts/jetson_csi_setup.sh"
"/home/$USER/Billiards-AI/scripts/jetson_csi_setup.sh"
```

Additional checks:

- verify camera ribbon orientation and secure connector lock
- ensure no competing process holds the camera
- restart Argus: `sudo /usr/bin/systemctl restart nvargus-daemon`
- if **`GStreamer`** is **NO** or **`import cv2`** loads pip OpenCV under **`.venv/site-packages`**, re-run **`bash scripts/setup_jetson_edge_venv.sh`** on the Jetson (see **`docs/DEPLOYMENT_JETSON.md`** for NumPy / user-site edge cases).
- if OpenCV import fails with `_ARRAY_API not found` or `numpy.core.multiarray failed to import`:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install --upgrade --force-reinstall "numpy<2"
```

- verify GStreamer pipeline manually (Jetson):

```bash
/usr/bin/timeout 10 gst-launch-1.0 -e nvarguscamerasrc sensor-id=0 ! \
  "video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1" ! \
  nvvidconv ! "video/x-raw,format=I420" ! \
  fakesink
```

## Docker alternative (recommended on Orin Nano)

```bash
cd "/home/$USER/Billiards-AI"
scripts/docker_jetson_build.sh
scripts/docker_jetson_up.sh
curl -s "http://127.0.0.1:8000/health"
curl -s "http://127.0.0.1:8001/mjpeg" >/dev/null
```
