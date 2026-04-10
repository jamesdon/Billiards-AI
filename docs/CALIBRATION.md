# Table calibration and homography

## Objective

Map pixel coordinates \((x, y)\) to table-plane coordinates \((X, Y)\) in meters so that:

- velocities and distances are meaningful
- pocket zones are stable
- event logic is independent of camera placement

## Approach

### 1) Manual 4-point calibration (baseline)

User clicks the four table corners in the camera view (or provides coordinates). Given:

- pixel points \(p_i = (x_i, y_i)\)
- corresponding table points \(P_i = (X_i, Y_i)\)

Compute homography \(H\) such that \(P \sim H p\).

This is robust and simple on edge hardware.

### 2) Automatic geometry derivation from corners (implemented)

This repo includes a helper (`edge/calib/table_geometry.py`) that derives
baseline table geometry from four image corners:

- homography `H`
- six standardized pockets
- table length/width
- kitchen polygon
- break area polygon

CLI workflow:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main \
  --auto-calib-out "/home/$USER/Billiards-AI/calibration.json" \
  --table-size 6ft \
  --table-corners-px "120,80;1160,80;120,640;1160,640"
```

Corner order for `--table-corners-px` is strictly:

1. top-left
2. top-right
3. bottom-left
4. bottom-right

These points are **table playfield corners** (the cushion intersection corners), **not**
the centers of pockets.

This is still a baseline and should be visually validated before match use.

### Optional interactive corner picker (recommended)

Use the helper script to click corners from a live frame instead of typing pixels:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
export PYTHONNOUSERSITE=1
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --csi-flip-method 6 \
  --out "/home/$USER/Billiards-AI/calibration.json" \
  --table-size 6ft
```

If your local script is older and does not accept `--csi-flip-method`, use:

```bash
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --flip 6 \
  --out "/home/$USER/Billiards-AI/calibration.json" \
  --table-size 6ft
```

If your local `edge.main` is also older and does not support `--auto-calib-out`,
the helper now writes `calibration.json` directly without calling `edge.main`.

Table size selection behavior in the helper:

- If you pass `--table-size`, that value is used directly.
- If you do not pass `--table-size`, the helper attempts to auto-detect from an
  existing output calibration file (the `--out` path) by reading:
  - `table_length_m` and `table_width_m`, or
  - pocket geometry fallback.
- If no prior calibration is available, it defaults to `9ft`.
- The helper then presents a menu allowing you to accept the detected/default
  value or choose `6ft` (bar box), `7ft`, `8ft`, `9ft`, or `snooker`.

### What TL/TR/BL/BR means

These points are **table cloth corners** (the cushion intersection points of the
playable rectangle), in this strict order:

1. `TL`: top-left cloth corner
2. `TR`: top-right cloth corner
3. `BL`: bottom-left cloth corner
4. `BR`: bottom-right cloth corner

They are **not** pocket centers.

Click order (corners of playable table surface, not pocket centers):

1. top-left
2. top-right
3. bottom-left
4. bottom-right

Controls:

- `r`: reset points
- `q` or `Esc`: quit without saving
- auto-saves when 4 points are collected

### Jetson camera orientation (repeatable)

If the live view is upside down and you want a vertical flip, use:

- `--csi-flip-method 6` (vertical mirror)

Common Jetson `nvvidconv` values used in this project:

- `0`: no transform
- `2`: rotate 180 degrees
- `6`: vertical mirror

For repeatable runs, set this in every CSI command you use (calibration + edge runtime).

## Table dimensions presets

Calibration stores:

- table length/width in meters
- pocket centers/radii (or polygons) in table coords
- kitchen and break area polygons in table coords

Presets can be created per table type (6ft bar box/7ft/8ft/9ft, snooker).

## Output artifact

Calibration is saved to JSON (see `edge/calib/calib_store.py`) containing:

- `image_points`: four corners (pixels)
- `table_points`: four corners (meters)
- `H`: 3x3 homography (float)
- `pockets`: pocket definitions in table coords with standardized labels
- `table_length_m`: inferred or configured table length
- `table_width_m`: inferred or configured table width
- `kitchen_polygon_xy_m`: polygon in table coordinates
- `break_area_polygon_xy_m`: polygon in table coordinates

### Pocket labels (standard)

- Top Left Corner
- Top Right Corner
- Bottom Left Corner
- Bottom Right Corner
- Left Side Pocket
- Right Side Pocket

