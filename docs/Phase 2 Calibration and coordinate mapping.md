# Phase 2: Calibration and coordinate mapping

## Goal

Validate calibration schema, pocket labels, and coordinate mapping assumptions.

## What is automated vs manual today

- **Automated derivation from calibration corners**:
  - homography `H` (from provided image corners + table preset)
  - table length/width in meters (from selected table preset)
  - six standardized pocket centers/radii
  - kitchen polygon (head-string quarter table length)
  - break area polygon (head quarter of table)
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

When `--table-size` is omitted, the helper shows a table-size menu and defaults
to the value detected from an existing `--out` calibration file (if present).

Table size menu options include:

- `6ft` (bar box)
- `7ft`
- `8ft`
- `9ft`
- `snooker`

If your local helper is an older script version, use:

```bash
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --flip 6 \
  --table-size 9ft \
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

These four points are the **table playing-surface corners** (cushion nose
intersections), **not pocket centers**.

This writes:

- `H`
- `table_length_m`, `table_width_m`
- `kitchen_polygon_xy_m`
- `break_area_polygon_xy_m`
- standard `pockets`

## 1) Validate pocket labels in calibration JSON

Create/edit calibration file:

```bash
cd "/home/$USER/Billiards-AI"
cat > "/home/$USER/Billiards-AI/calibration.json" <<'EOF'
{
  "H": [[1,0,0],[0,1,0],[0,0,1]],
  "pockets": [
    {"label":"top_left_corner","center_xy_m":[0.0,0.0],"radius_m":0.07},
    {"label":"top_right_corner","center_xy_m":[2.84,0.0],"radius_m":0.07},
    {"label":"bottom_left_corner","center_xy_m":[0.0,1.42],"radius_m":0.07},
    {"label":"bottom_right_corner","center_xy_m":[2.84,1.42],"radius_m":0.07},
    {"label":"left_side_pocket","center_xy_m":[0.0,0.71],"radius_m":0.07},
    {"label":"right_side_pocket","center_xy_m":[2.84,0.71],"radius_m":0.07}
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

