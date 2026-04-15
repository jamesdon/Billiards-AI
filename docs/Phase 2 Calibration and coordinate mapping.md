# Phase 2: Calibration and coordinate mapping

## Goal

Validate calibration schema, pocket labels, and coordinate mapping assumptions.

`scripts/phase2.sh` is **headless** (writes a baseline JSON, runs `edge.main` smoke checks). It does **not** open the OpenCV calibration GUI. For the click-to-calibrate window, run `scripts/start_calibration.sh` (on the Nano desktop, or with X11 forwarding over SSH).

## What is automated vs manual today

- **Automated derivation from calibration corners**:
  - homography `H` (from provided image corners + table preset)
  - table length/width in meters (from selected table preset)
  - six standardized pocket centers/radii
  - kitchen polygon (head-string quarter from the kitchen short rail along X)
  - break area polygon (foot half-table / behind break line from kitchen)
- **Still manual/assisted**:
  - initial table corner selection in image pixel coordinates
  - optional override of pocket radii and exact break-zone policy

## 0) Generate calibration with table geometry automation

Use one command after selecting four corners manually (or from a helper click tool):

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main \
  --auto-calib-out "/home/$USER/Billiards-AI/calibration.json" \
  --table-size 9ft \
  --table-corners-px "120,90;1160,95;110,640;1170,645"
```

### Optional: interactive corner-click helper (recommended)

Preferred single-command startup (local disk, no git sync required):

```bash
cd "/home/$USER/Billiards-AI"
"/home/$USER/Billiards-AI/scripts/start_calibration.sh"
```

This launcher:

- activates `/home/$USER/Billiards-AI/.venv`
- exports `PYTHONNOUSERSITE=1`
- runs a local script self-check for required GUI features (flip/zoom/rotate/pan)
- runs an OpenCV/NumPy ABI guard; if it detects `_ARRAY_API` / `multiarray`
  import mismatch on Jetson-style setups, it auto-reinstalls `numpy<2` in the
  active venv before launching
- starts `scripts/calib_click.py` from local disk
- writes `calibration.json` to `/home/$USER/Billiards-AI/calibration.json` by default

Optional overrides:

```bash
cd "/home/$USER/Billiards-AI"
CSI_SENSOR_ID=0 CSI_FLIP_METHOD=6 CSI_OPEN_RETRIES=12 \
  CALIB_OUT="/home/$USER/Billiards-AI/calibration.json" \
  "/home/$USER/Billiards-AI/scripts/start_calibration.sh"
```

If Argus reports `Failed to create CaptureSession`, close other camera users, run
`sudo systemctl restart nvargus-daemon`, and retry `CSI_FLIP_METHOD` (0, 2, 6) and
`CSI_SENSOR_ID`. The calibration GUI always uses a live camera (CSI/USB per `--camera`).

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --csi-flip-method 6 \
  --out "/home/$USER/Billiards-AI/calibration.json"
```

The helper now opens with auto-detected corner proposals and in-window controls:

- **Corner points** are auto-proposed from a table-like quadrilateral fit and
  then refined by edge-line intersection fitting and local corner-feature
  snapping for better first-pass placement on real camera images.
- Left-click near a point to drag it.
- `r` resets corners back to fresh auto-detection.
- The in-window menu panel is automatically placed in a low-conflict region
  away from the detected corners so corner dragging stays accessible.
- **View controls** are available directly in the overlay:
  - Flip horizontal and flip vertical toggles (clickable radios).
  - Zoom in/out controls (clickable `+/-` buttons and keyboard).
  - Rotate controls (`Rot-` / `Rot+` in overlay).
  - Pan controls (clickable directional buttons and keyboard arrows / `i j k l`).
  - Fine/coarse view-step radios (default is **Fine**).
  - Reset-view button to return to default framing.
  - Double-click the panel header to collapse/expand the tools accordion.
  - These are display-only transforms for calibration UX; saved calibration
    points remain in source image coordinates.
  - Overlay layout now auto-scales to stay fully on-screen so controls remain clickable.
- The helper uses the CLI-selected camera source only (no in-UI camera source
  menu), which removes startup probing overhead and keeps launch latency low.
- During editing, camera preview is continuously refreshed from the active
  capture stream so pan/zoom/rotate adjustments match current table state.
- **Table size** uses an on-screen radio list only (no CLI table-size selection).
- **Units** use an on-screen radio toggle (`imperial` default, `metric` optional).
- **Side pockets** are not edited in the GUI anymore (they drifted on some setups).
  Saved `calibration.json` still includes `left_side_pocket` / `right_side_pocket`
  entries: positions are taken from the homography defaults (mid long-rails) when
  you save, or from `edge.calib` auto-calibration when that path succeeds.

Table size menu options include:

- `6ft` (bar box)
- `7ft`
- `8ft`
- `9ft`
- `snooker`

Unit toggle options:

- `imperial` (default UI display)
- `metric`

If your local helper is an older script version, use:

```bash
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --flip 6 \
  --out "/home/$USER/Billiards-AI/calibration.json"
```

If your local `edge.main` is older and does not support `--auto-calib-out`, the
updated `scripts/calib_click.py` still writes `calibration.json` directly (no
`edge.main` auto-calibration CLI needed).

`--csi-flip-method` is passed directly to Jetson `nvvidconv flip-method`:

- `0`: no rotation/flip
- `6`: vertical mirror (use this for vertically flipped view)
- `2`: 180-degree rotate (if the camera is physically upside-down)

The helper asks you to click corners in order:

1. top-left
2. top-right
3. bottom-left
4. bottom-right

These four points are the **outside corners of the table playing surface**
(outside cushion/corner intersections), **not pocket centers**.

View controls (keyboard):

- `h`: toggle horizontal flip for the preview
- `v`: toggle vertical flip for the preview
- `+` / `=` / `]`: zoom in
- `-` / `_` / `[`: zoom out
- `z` / `,`: rotate left (counter-clockwise)
- `x` / `.`: rotate right (clockwise)
- arrow keys or `i`/`j`/`k`/`l`: pan
- click `Fine` / `Coarse` radio in the overlay to set adjustment step size (default: Fine)
- `0`: reset view transforms

This writes:

- `H`
- `table_length_m`, `table_width_m`
- `kitchen_polygon_xy_m`
- `break_area_polygon_xy_m`
- standard `pockets` (corner + side pockets; side pocket meters from defaults or edge auto-calib)

## 1) Validate pocket labels in calibration JSON

Create/edit calibration file:

```bash
cd "/home/$USER/Billiards-AI"
cat > "/home/$USER/Billiards-AI/calibration.json" <<'EOF'
{
  "H": [[1,0,0],[0,1,0],[0,0,1]],
  "pockets": [
    {"label":"top_left_corner","center_xy_m":[0.0,0.0],"radius_m":0.07},
    {"label":"top_right_corner","center_xy_m":[0.0,1.42],"radius_m":0.07},
    {"label":"bottom_left_corner","center_xy_m":[2.84,0.0],"radius_m":0.07},
    {"label":"bottom_right_corner","center_xy_m":[2.84,1.42],"radius_m":0.07},
    {"label":"left_side_pocket","center_xy_m":[1.42,0.0],"radius_m":0.07},
    {"label":"right_side_pocket","center_xy_m":[1.42,1.42],"radius_m":0.07}
  ]
}
EOF
```

## 2) Load calibration in edge startup

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --calib "/home/$USER/Billiards-AI/calibration.json" --mjpeg-port 8080
```

## 3) Negative test: invalid pocket label should fail

```bash
cd "/home/$USER/Billiards-AI"
cp "/home/$USER/Billiards-AI/calibration.json" "/home/$USER/Billiards-AI/calibration_invalid.json"
python - <<'PY'
import json
p="/home/$USER/Billiards-AI/calibration_invalid.json"
d=json.load(open(p))
d["pockets"][0]["label"]="top_middle_side"
json.dump(d, open(p,"w"), indent=2)
print("written", p)
PY
```

Run and confirm error:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --calib "/home/$USER/Billiards-AI/calibration_invalid.json" --mjpeg-port 8081
```

## Pass criteria

- valid `calibration.json` loads successfully
- invalid label is rejected
- derived table geometry (kitchen + break area) is present when calibration includes corners

## Troubleshooting note from field run (Jetson Orin Nano)

If Phase 2 fails at edge startup with:

`RuntimeError: Failed to open camera source='nvarguscamerasrc ...'`

and `nvgstcapture-1.0` or `gst-launch-1.0` works, the usual issue is Python
OpenCV build mismatch (venv wheel without GStreamer).

Verify:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python - <<'PY'
import cv2
print("cv2_path:", cv2.__file__)
for ln in cv2.getBuildInformation().splitlines():
    if "GStreamer" in ln:
        print(ln)
PY
```

If this shows `GStreamer: NO`, uninstall pip OpenCV wheels and rely on distro
`python3-opencv` in a `--system-site-packages` venv before retrying Phase 2.

If OpenCV import fails with NumPy ABI errors like:

- `AttributeError: _ARRAY_API not found`
- `ImportError: numpy.core.multiarray failed to import`

then pip likely installed NumPy 2.x while Jetson distro OpenCV was built against
NumPy 1.x. Pin NumPy `<2` in the venv and rerun Phase 2.

If Phase 2 fails with `OSError: [Errno 98] Address already in use` when binding the
MJPEG HTTP server, another process (often a previous `edge.main`) is already using
that port. `scripts/phase2.sh` leaves `MJPEG_PORT` unset by default and chooses the
first free port in `18080–18255` on `127.0.0.1` for the valid-calibration smoke; the
invalid-label check uses `MJPEG_PORT+1`. To force a specific port, run with
`MJPEG_PORT=8080 bash scripts/phase2.sh` (or stop the process holding the port).

If the log shows Argus / CSI errors such as `Failed to create CaptureSession` or
`gstnvarguscamerasrc` failures, the MJPEG byte probe may fail if the pipeline never
delivers frames (and the process may exit once the capture error is surfaced). Stop
other consumers of the camera (including background `edge.main` or `nvgstcapture`),
power-cycle the camera module if needed, retry `--csi-flip-method` values `0` and
`6`, and confirm `--csi-sensor-id` matches your wiring. `edge.main` binds MJPEG at the start of `main()` (before calibration load) and
uses a threaded HTTP server so a long-lived `/mjpeg` connection cannot block
`/health`. Note that Python still imports `edge.main` and its dependencies before
`main()` runs, so the port may not open instantly on a cold Jetson; `scripts/phase2.sh`
waits for the MJPEG TCP port to accept connections (up to about 60 seconds) before
curling `/health`.

