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

Corner order for `--table-corners-px` is strictly **physical** (not “image top-left”):

1. **TL** — head short rail (kitchen / rack side), left long-rail corner  
2. **TR** — same head short rail, right long-rail corner  
3. **BL** — foot short rail (behind the break line from the kitchen), left long-rail corner  
4. **BR** — same foot short rail, right long-rail corner  

Table coordinates use **X** from head toward foot and **Y** along the head rail from TL to TR, so corner pockets are **(0,0), (0,W), (L,0), (L,W)** and side pockets sit at **mid-span on each long rail**: **(L/2,0)** and **(L/2,W)**.

### Where to place the four corner calibration points (recommended)

For best downstream geometry (pocket zones, rail logic, fine alignment), the four
image points should sit at each **corner pocket’s inner throat**: the point where
the two **playing-surface** rail guidelines—long rail and short rail—would intersect
if extended into the pocket (the inside corner of the pocket mouth), **not** the
pocket center and **not** the outer cushion nose.

Older text in this doc referred to “outside corners of the playable rectangle” as a
first-order mental model; the **intended click target** for interactive calibration
matches the inner throat / rail intersection above. Homography still maps those
four pixels to \((0,0), (0,W), (L,0), (L,W)\) in table meters.

Validate visually on your table before match use.

### Optional interactive corner picker (recommended)

Single-command startup script (preferred):

```bash
cd "/home/$USER/Billiards-AI"
"/home/$USER/Billiards-AI/scripts/start_calibration.sh"
```

`start_calibration.sh` now includes a NumPy/OpenCV ABI guard. If local
packages drift (for example NumPy 2.x with distro OpenCV on Jetson built against
NumPy 1.x), it automatically repairs the venv by reinstalling `numpy<2` before
launching the GUI.

This script runs fully from local disk (no git operations), activates the local
venv, enforces `PYTHONNOUSERSITE=1`, validates `scripts/calib_click.py` for the
expected view-control code paths in `calib_click.py`, then launches the calibration window.

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

### Jetson CSI: `Failed to open camera` / Argus

The default path uses `nvarguscamerasrc` (GStreamer). If OpenCV cannot open it:

1. Stop other camera users, then `sudo systemctl restart nvargus-daemon` (reboot if it stays wedged).
2. Try another sensor or mode via **environment** (`CSI_SENSOR_ID`, `CSI_FLIP_METHOD`, `FRAME_WIDTH`, etc.) or by appending **extra CLI args** (they override the script’s defaults because they are passed last):

```bash
bash "/home/$USER/Billiards-AI/scripts/start_calibration.sh" --width 640 --height 480 --csi-framerate 15
bash "/home/$USER/Billiards-AI/scripts/start_calibration.sh" --camera 0
```

`--camera 0` selects **V4L2** device index 0 (`/dev/video0`), which on many Jetson images is a usable path when the raw nvargus pipeline string fails from OpenCV.

**Diagnostics on Jetson (typical):** `dmesg` often requires **`sudo dmesg`** (`Operation not permitted` otherwise). If **`ls /dev/video*`** finds nothing **and** `nvarguscamerasrc` reports **No cameras available**, the board is not exposing a camera to the OS (missing or mis-seated CSI module, wrong port, or no supported sensor in the device tree)—software flags alone will not fix that until hardware enumerates.

**Calibration is not YOLO training.** Setting table corners and saving `calibration.json` only requires a working camera + `calib_click` / `start_calibration.sh`. The YOLO folder `data/datasets/billiards/images/train` is for **detector training** (`jetson_yolo_train.sh`) later; you can ignore it until you intentionally train a model.

In-window workflow (new default):

- The helper proposes initial corners from the current frame, then **refines each
  corner toward the corner-pocket inner throat** by intersecting two offset lines
  parallel to the adjacent rails, fit to Canny edges in the pocket wedge (see
  `_pocket_throat_from_seed` in `scripts/calib_click.py`). If that step fails
  (too few edges), it falls back to the previous Hough-quad + subpixel path.
  Always verify on your table; drag handles if a pocket is weak in the image.
  - It combines contour/rectangle fitting, adaptive edge thresholds, and Hough-line
    side fitting with corner-feature refinement for tighter initial TL/TR/BL/BR placement.
  - Auto-detect **does not** maximize quad area alone (that often locks onto the whole
    room boundary). It prefers quadrilaterals in a **table-sized area band** with
    vertices **inset from the image border**, then applies throat / Hough refinement.
  - Physical **TL/TR/BL/BR** vs image-up is ambiguous when the kitchen is at the top
    or bottom of the frame; the script tries **both** short-rail orientations and
    keeps the labeling closest to image-axis corner order from the same four points.
- You can drag any point to refine it.
- The table-size/units panel is automatically placed in a low-conflict area of the
  frame (away from corner points) so corner dragging remains clickable.
- The overlay no longer renders a large text banner across the top of the frame;
  controls/status are consolidated in the right-side panel to keep points visible.
- With four corners and a selected table size, the **video** shows the **kitchen** (head
  rail to head string) and a **foot quarter** reference (tinted polygons), plus a **cyan
  line** for the **head string** (the official “break line” — across the long rails, often
  approximated at ¼ of playing length from the head, i.e. second-diamond to second-diamond on
  standard tables). The **table outline** follows perimeter order (TL–TR–BR–BL, not a
  bowtie). Use **Re-detect** in the SETUP column or `r` to re-run auto pocket-corner detection.
- The tools panel header supports:
  - drag to reposition
  - double-click to collapse/expand (accordion behavior) for unobstructed corner editing
- View controls are now available directly in the panel:
  - flip horizontal / flip vertical (GUI toggles)
  - zoom in / zoom out
  - rotate left / rotate right
  - pan up / left / right / down
  - fine/coarse radio selector for zoom/rotate/pan increment size (defaults to `fine`:
    **fine** = 0.5° rotation and 1% pan; **coarse** = 2° and 3% pan)
  - reset view
  - when pan/zoom would show pixels outside the camera frame, the preview fills
    that region with **black** (not a smeared copy of the image border); the live
    frame is still only the sensor rectangle.
  - these are view-only transforms for easier editing after camera moves; saved
    calibration points remain in source image coordinates.
- Camera source switching controls were removed from the overlay to reduce startup
  latency and simplify editing. The selected CLI camera source remains the single
  active source for the session.
- Preview is continuously refreshed from the selected camera stream while editing
  (live background), with automatic reconnect attempts if frame reads fail; point
  coordinates remain in source image space.
- Edit modes:
  - outside corners mode (`TL/TR/BL/BR`)
  - side pockets mode (`LS/RS`)
  - in side-pocket mode, both `LS` and `RS` are draggable; they are **anchored to the
    center line of each long rail** (TL–BL and TR–BR) after auto-seeding
  - side-pocket seeds use dark circular pocket mouths (threshold + morphology +
    optional Hough circles), then snap to the long-rail segment; drag to adjust
- Table-size is selected in-window via radio list:
  - click radio circles or press keys `1..5`
  - options: `6ft (bar box)`, `7ft`, `8ft`, `9ft`, `snooker`
  - detected/default option is preselected from previous calibration file when available
- `--table-size` is intentionally not used by this GUI workflow; selection happens in-window.
- Unit display toggle uses an in-window radio list:
  - click radio circles or press `6` (`imperial`) / `7` (`metric`)
  - default UI unit is `imperial`

### What TL/TR/BL/BR means

These are the **outside cushion corners** of the playfield, in **physical** order (not “image top-left”):

1. `TL` / `TR` — the two corners on the **head short rail** (kitchen / rack side)
2. `BL` / `BR` — the two corners on the **foot short rail** (opposite the kitchen; behind the break line from the kitchen)

Within each short rail, `L` / `R` follow **left** vs **right** as seen from above the table (smaller image **x** = `L` when the table is not flipped).

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
- `g`: keyboard toggle for view step mode (`fine`/`coarse`)
- `0`: reset view transform

### Jetson-family CSI camera orientation (repeatable)

If the live view is upside down and you want a vertical flip, use:

- `--csi-flip-method 6` (vertical mirror)

Common `nvvidconv` values on Jetson CSI pipelines in this project:

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
- Optional `H_projector` (or alias `H_table_to_projector` on load): 3×3 overhead **projector** homography using the same `Homography` convention as `H` (see `core/geometry.py`): **`to_pixel(xy_m)`** maps table meters to projector framebuffer pixels. Used for a mirrored inset in `edge/overlay/draw.py` and for a future full projector render target.

### Pocket labels (standard)

- Top Left Corner
- Top Right Corner
- Bottom Left Corner
- Bottom Right Corner
- Left Side Pocket
- Right Side Pocket

