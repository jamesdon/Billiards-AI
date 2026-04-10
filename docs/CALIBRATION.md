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
  --table-size 9ft \
  --table-corners-px "120,80;1160,80;120,640;1160,640"
```

Corner order for `--table-corners-px` is strictly:

1. top-left
2. top-right
3. bottom-left
4. bottom-right

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
  --table-size 9ft
```

If your local script is older and does not accept `--csi-flip-method`, use:

```bash
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --flip 6 \
  --out "/home/$USER/Billiards-AI/calibration.json" \
  --table-size 9ft
```

If your local `edge.main` is also older and does not support `--auto-calib-out`,
the helper now writes `calibration.json` directly without calling `edge.main`.

Click order:

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

Presets can be created per table type (7ft/8ft/9ft, snooker).

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

