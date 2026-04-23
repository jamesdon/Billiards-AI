# Phase 1: Environment and startup

## Goal

Bring up edge + backend reliably and verify core services.

## Phase 1 status notes (NVIDIA CSI on Jetson Orin Nano)

- Backend and software integrity checks can pass independently of camera bring-up.
- For this project, a **CSI camera is always intended** for edge runtime validation on the Orin Nano (JetPack 5.x).
- If CSI camera open fails (`RuntimeError: Failed to open camera source='nvarguscamerasrc ...'`), treat Phase 1 as blocked on device camera stack readiness.

## 1) Create and activate environment

Install venv support first (required on minimal Ubuntu / L4T images):

```bash
sudo /usr/bin/apt-get update
sudo /usr/bin/apt-get install -y python3-venv python3-pip
```

If `python3 -m venv` reports `ensurepip is not available`, install the versioned package matching your Python runtime and retry:

```bash
/usr/bin/python3 --version
sudo /usr/bin/apt-get install -y "python3.10-venv"
```

Then create and activate the virtual environment:

```bash
cd "/home/$USER/Billiards-AI"
/usr/bin/python3 -m venv --system-site-packages "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m pip install -U pip
# Install non-OpenCV deps first on device, then force-remove any pip OpenCV wheel.
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless || true
# Also clean user-site packages that can shadow system cv2.
/usr/bin/python3 -m pip uninstall -y --break-system-packages opencv-python opencv-contrib-python opencv-python-headless || true
# Ensure NumPy remains compatible with distro OpenCV ABI.
python -m pip install --upgrade "numpy<2"
```

Edge note: this project expects **distro** OpenCV (`python3-opencv`) with GStreamer for CSI on Jetson.
Avoid installing `opencv-python` from pip on-device (wheel builds typically lack the CSI pipeline).

## 2) Quick integrity checks

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 180 python -m compileall "/home/$USER/Billiards-AI/core" "/home/$USER/Billiards-AI/edge" "/home/$USER/Billiards-AI/backend"
/usr/bin/timeout 120 ruff check "/home/$USER/Billiards-AI"
/usr/bin/timeout 300 pytest -q "/home/$USER/Billiards-AI/tests"
```

## 3) Start backend

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8780
```

In another terminal:

```bash
curl -s "http://127.0.0.1:8780/health"
curl -s "http://127.0.0.1:8780/live/state"
```

## 4) Start edge (no model smoke test)

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python -m edge.main --camera csi --csi-sensor-id 0 --mjpeg-port 8080
```

To vertically flip the CSI camera image, add `--csi-flip-method 6`:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --mjpeg-port 8080
```

In another terminal:

```bash
curl -s "http://127.0.0.1:8080/mjpeg" >/dev/null
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
- verify OpenCV has GStreamer enabled:

```bash
python - <<'PY'
import cv2
import site
print("OpenCV:", cv2.__version__)
print("cv2_path:", cv2.__file__)
print("user_site:", site.getusersitepackages())
print("GStreamer:", "YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "NO")
PY
```

- if `cv2_path` points under `/home/$USER/.local/...`, disable user-site packages:

```bash
export PYTHONNOUSERSITE=1
```

- if GStreamer shows `NO`, rebuild the venv without pip OpenCV and install distro OpenCV:

```bash
sudo /usr/bin/apt-get install -y python3-opencv
cd "/home/$USER/Billiards-AI"
/usr/bin/rm -rf "/home/$USER/Billiards-AI/.venv"
/usr/bin/python3 -m venv --system-site-packages "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless || true
# Also clean user-site packages that can shadow system cv2.
/usr/bin/python3 -m pip uninstall -y --break-system-packages opencv-python opencv-contrib-python opencv-python-headless || true
```
- note: some pip resolver runs on aarch64 can still select `opencv-python`; always verify with:

```bash
python - <<'PY'
import cv2
print("cv2_path:", cv2.__file__)
for ln in cv2.getBuildInformation().splitlines():
    if "GStreamer" in ln:
        print(ln)
PY
```
- if OpenCV import fails with `_ARRAY_API not found` or
  `numpy.core.multiarray failed to import`, force NumPy 1.x and retry:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m pip install --upgrade --force-reinstall "numpy<2"
```
- verify GStreamer pipeline manually:

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
curl -s "http://127.0.0.1:8780/health"
curl -s "http://127.0.0.1:8080/mjpeg" >/dev/null
```

