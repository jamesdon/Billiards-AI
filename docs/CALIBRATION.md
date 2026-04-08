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

### 2) Automatic corner detection (optional)

If table rails are visually distinct, detect rectangle via edges/lines and refine using RANSAC.
This is optional; manual is the default for reliability.

## Table dimensions presets

Calibration stores:

- table length/width in meters
- pocket centers/radii (or polygons) in table coords

Presets can be created per table type (7ft/8ft/9ft, snooker).

## Output artifact

Calibration is saved to JSON (see `edge/calib/calib_store.py`) containing:

- `image_points`: four corners (pixels)
- `table_points`: four corners (meters)
- `H`: 3x3 homography (float)
- `pockets`: pocket definitions in table coords with standardized labels

### Pocket labels (standard)

- Top Left Corner
- Top Right Corner
- Bottom Left Corner
- Bottom Right Corner
- Left Side Pocket
- Right Side Pocket

