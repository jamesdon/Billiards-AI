# Model optimization (ONNX → TensorRT)

## Detector choice

Use a small model class (YOLOv8n / YOLOv5n / custom tiny) trained for:

- billiard balls (optionally per-type labels)
- cue ball
- optionally cue stick

## Export to ONNX

Preferred: export with static input shape (e.g., 416×416) and FP16 when available.

## ONNXRuntime baseline

ONNXRuntime is the default runtime in this repo for portability. On Jetson you’ll want the Jetson-compatible build.

## TensorRT (recommended on Jetson)

Convert ONNX to TensorRT engine:

- FP16 is usually the best trade-off on Nano.
- INT8 requires calibration and can be fragile; use only if needed.

## Runtime knobs

- inference every N frames (2–3)
- smaller input resolution
- reduce max detections and NMS candidates

