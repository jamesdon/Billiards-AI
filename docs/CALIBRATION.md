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

These points are the **outside corners of the playable table rectangle**
(the cushion intersection corners), **not** the centers of pockets.

This is still a baseline and should be visually validated before match use.

### Optional interactive corner picker (recommended)

Single-command startup script (preferred):

```bash
cd "/home/$USER/Billiards-AI"
"/home/$USER/Billiards-AI/scripts/start_calibration.sh"
```

This script runs fully from local disk (no git operations), activates the local
venv, enforces `PYTHONNOUSERSITE=1`, validates `scripts/calib_click.py` for the
expected GUI view controls, and then launches the calibration window.

Use the helper script to launch an interactive calibration window:

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

If your local script is older and does not accept `--csi-flip-method`, use:

```bash
python "/home/$USER/Billiards-AI/scripts/calib_click.py" \
  --camera csi \
  --csi-sensor-id 0 \
  --flip 6 \
  --out "/home/$USER/Billiards-AI/calibration.json"
```

If your local `edge.main` is also older and does not support `--auto-calib-out`,
the helper now writes `calibration.json` directly without calling `edge.main`.

In-window workflow (new default):

- The helper proposes table outside-corner points automatically from the current frame.
  - It now combines contour/rectangle fitting with local corner-feature refinement for
    tighter initial TL/TR/BL/BR placement.
- You can drag any point to refine it.
- The table-size/units panel is automatically placed in a low-conflict area of the
  frame (away from corner points) so corner dragging remains clickable.
- View controls are now available directly in the panel:
  - flip horizontal / flip vertical (GUI toggles)
  - zoom in / zoom out
  - rotate left / rotate right
  - pan up / left / right / down
  - reset view
  - these are view-only transforms for easier editing after camera moves; saved
    calibration points remain in source image coordinates.
- Edit modes:
  - outside corners mode (`TL/TR/BL/BR`)
  - side pockets mode (`LS/RS`)
- Table-size is selected in-window via radio list:
  - click radio circles or press keys `1..5`
  - options: `6ft (bar box)`, `7ft`, `8ft`, `9ft`, `snooker`
  - detected/default option is preselected from previous calibration file when available
- `--table-size` is intentionally not used by this GUI workflow; selection happens in-window.
- Unit display toggle uses an in-window radio list:
  - click radio circles or press `6` (`imperial`) / `7` (`metric`)
  - default UI unit is `imperial`

### What TL/TR/BL/BR means

These points are the **outside corners of the table play area**
(the cushion intersection points of the playable rectangle), in this strict order:

1. `TL`: top-left outside corner
2. `TR`: top-right outside corner
3. `BL`: bottom-left outside corner
4. `BR`: bottom-right outside corner

They are **not** pocket centers.

Controls:

- drag points to adjust
- `r`: reset to auto-detected corners
- `q` or `Esc`: quit without saving
- `Enter`: save calibration
- `u`: undo the most recent point in current mode
- `t`: toggle units (imperial/metric)
- `6`: select imperial units, `7`: select metric units
- `m`: toggle side-pocket edit mode
- `h`: toggle horizontal view flip
- `v`: toggle vertical view flip
- `+` / `-`: zoom in / out
- `z` / `x` (or `,` / `.`): rotate view left / right
- arrow keys or `i/j/k/l`: pan up/left/down/right
- `0`: reset view transform

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

