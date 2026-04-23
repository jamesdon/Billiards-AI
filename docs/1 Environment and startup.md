# 1. Environment and startup

## Goal

Bring up edge + backend reliably and verify core services.

## 0) Detect your machine (run first)

Paste **one** of these; the output tells you which setup block to follow.

```bash
/usr/bin/uname -s
/usr/bin/uname -m
```

| `uname -s` | `uname -m` | Follow |
|------------|------------|--------|
| `Linux` | `aarch64` or `arm64` | **§1a — Linux ARM64 (Jetson-family, CSI)** |
| `Linux` | `x86_64` (or other) | **§1b — Linux x86_64 (dev workstation)** |
| `Darwin` | `arm64` or `x86_64` | **§1c — macOS** |
| anything else | — | **§1d — Other** |

Optional one-liner label:

```bash
case "$(/usr/bin/uname -s)-$(/usr/bin/uname -m)" in
  Linux-aarch64|Linux-arm64) echo "USE_SECTION_1a_JETSON_ARM64" ;;
  Linux-x86_64) echo "USE_SECTION_1b_LINUX_X86_64" ;;
  Darwin-arm64|Darwin-x86_64) echo "USE_SECTION_1c_MACOS" ;;
  *) echo "USE_SECTION_1d_OTHER" ;;
esac
```

## 1.1 Status notes (NVIDIA CSI on Jetson Orin Nano)

- Backend and software integrity checks can pass independently of camera bring-up.
- For this project, a **CSI camera is always intended** for edge runtime validation on the Orin Nano (JetPack 5.x). That path requires **Linux ARM64** and **OpenCV with GStreamer** (§1a).
- If CSI camera open fails (`RuntimeError: Failed to open camera source='nvarguscamerasrc ...'`), treat this section as blocked on device camera stack readiness (see **CSI troubleshooting** at the end).

## 1) Create and activate the environment

Use **exactly one** subsection below for your platform from §0.

### 1a) Linux ARM64 — Jetson-family (CSI, distro OpenCV)

`requirements.txt` does **not** install `opencv-python` on `aarch64`/`arm64`. Use **apt** `python3-opencv` (GStreamer) and a venv with **`--system-site-packages`**. Do **not** install `requirements-train.txt` in this venv if you need CSI (Ultralytics pulls pip OpenCV and you often get **`GStreamer: NO`**).

```bash
cd "/home/$USER/Billiards-AI"
sudo /usr/bin/apt-get update
sudo /usr/bin/apt-get install -y python3-venv python3-pip python3-opencv python3-gst-1.0 gstreamer1.0-tools
```

If `python3 -m venv` reports `ensurepip is not available`:

```bash
/usr/bin/python3 --version
sudo /usr/bin/apt-get install -y "python3.10-venv"
```

Create the venv, install Python deps, pin NumPy for distro OpenCV ABI:

```bash
cd "/home/$USER/Billiards-AI"
/usr/bin/rm -rf "/home/$USER/Billiards-AI/.venv"
/usr/bin/python3 -m venv --system-site-packages "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m pip install -U pip wheel
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true
/usr/bin/python3 -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless 2>/dev/null || true
for _cv in "/home/$USER"/.local/lib/python3.*/site-packages/cv2*; do [ -e "$_cv" ] && /usr/bin/rm -rf "$_cv"; done
python -m pip install --upgrade "numpy<2"
python - <<'PY'
import cv2
print("cv2_path:", cv2.__file__)
print("GStreamer:", "YES" if "GStreamer:                   YES" in cv2.getBuildInformation() else "NO")
PY
```

Expect **`cv2_path`** under **`/usr/lib/python3/dist-packages/`** (or similar) and **`GStreamer: YES`**. If you see **`…/.venv/…/cv2`** or **`GStreamer: NO`**, run the **repair** block in **`README.md`** (“Repair when checks show pip OpenCV … or `GStreamer: NO`”) or **`docs/DEPLOYMENT_JETSON.md`**.

### 1b) Linux x86_64 — developer workstation

Plain venv is fine; `requirements.txt` installs **`opencv-python`** via pip.

```bash
cd "/home/$USER/Billiards-AI"
/usr/bin/python3 -m venv "/home/$USER/Billiards-AI/.venv"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards-AI/requirements.txt"
python - <<'PY'
import cv2
print("cv2_path:", cv2.__file__)
PY
```

Edge default is **`--camera csi`** (Jetson). On x86 there is usually no CSI stack — use **`--camera usb`**, a numeric V4L2 index, or a **video file** path instead (see `python -m edge.main --help`).

### 1c) macOS (Darwin)

Plain venv; pip **`opencv-python`** from `requirements.txt`. GStreamer is **not** required for typical USB webcams.

```bash
cd "/home/$USER/Billiards-AI"
python3 -m venv ".venv"
source ".venv/bin/activate"
export PYTHONNOUSERSITE=1
python3 -m pip install -U pip
python3 -m pip install -r "requirements.txt"
python3 - <<'PY'
import cv2
print("cv2_path:", cv2.__file__)
PY
```

Start edge with USB (not CSI), for example:

```bash
cd "/home/$USER/Billiards-AI"
source ".venv/bin/activate"
python3 -m edge.main --camera usb --usb-index 0 --mjpeg-port 8001
```

### 1d) Other platforms

Use the closest match: **§1b** for generic Linux without Jetson CSI, **§1c** for macOS-like dev. For production Jetson CSI, use **§1a** on **Linux ARM64** only. See **`README.md`**, **`docs/DEPLOYMENT_JETSON.md`**, and **`docs/PORTS.md`**.

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
./scripts/run_backend.sh
```

For the **interactive setup guide**, use the same API and open **`http://127.0.0.1:8000/setup`** (see **`README.md`**). Prefer **`scripts/run_backend.sh`** over bare `uvicorn` (stale `.venv/bin/uvicorn` shebang after renames; port-in-use message). Equivalent: venv active, `python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000`.

In another terminal:

```bash
curl -s "http://127.0.0.1:8000/health"
curl -s "http://127.0.0.1:8000/live/state"
```

## 4) Start edge (no model smoke test)

**Linux ARM64 (Jetson CSI)** — default camera is CSI:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python3 -m edge.main --camera csi --csi-sensor-id 0 --mjpeg-port 8001
```

To vertically flip the CSI camera image, add `--csi-flip-method 6`:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
/usr/bin/timeout 1200 python3 -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --mjpeg-port 8001
```

**macOS or Linux x86 without CSI** — use USB or a file, for example:

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
- verify OpenCV has GStreamer enabled (Linux ARM64 / §1a):

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

- if `cv2_path` points under `/home/$USER/.local/...`, disable user-site packages: `export PYTHONNOUSERSITE=1` (already in §1a).
- if **`GStreamer`** shows **`NO`** on Jetson, you are not on the §1a stack — use **`README.md`** repair block or **`docs/DEPLOYMENT_JETSON.md`** (remove pip OpenCV, distro `python3-opencv`, `--system-site-packages` venv, reinstall **`requirements.txt`** only for CSI).
- if OpenCV import fails with `_ARRAY_API not found` or `numpy.core.multiarray failed to import`, force NumPy 1.x and retry:

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
