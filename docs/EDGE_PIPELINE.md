# Edge pipeline (real-time)

Baseline device: **Jetson Orin Nano** (JetPack 5.x class stack). The pipeline is **CSI-first** (GStreamer / `nvarguscamerasrc`), **ONNX Runtime** by default, and **TensorRT FP16** as the recommended production detector backend when you need maximum FPS.

## Module graph

```text
Capture -> (optional resize) -> Detect (every N frames) -> Track (every frame)
  -> Classify (ROI) -> Table coords -> Event detectors -> Rules -> Stats -> Overlay -> Stream
```

## Streaming protocols (common options)

- **MJPEG over HTTP**: simplest, lowest integration cost, works everywhere; higher bandwidth.
- **RTSP**: common for CCTV/NVR ingestion; good for LAN.
- **WebRTC**: best for low-latency browser viewing; more setup, NAT traversal.
- **HLS/DASH (optional)**: high latency; good for “watch later” or cloud distribution.
- **SRT (optional)**: robust low-latency contribution stream; common in broadcast workflows.

Baseline in this repo is MJPEG; RTSP/WebRTC publishers are planned as optional modules.

## Stats + progress tracking (real time)

Computed on edge:

- Ball speeds (per ball)
- Cue-ball peak speed per shot
- Shot duration
- Turn/inning counters (player + team aware)
- Pocketed balls per player and per team
- Fouls per player and per team

## Player + stick detection (optional)

If your detector model includes `person` and `cue_stick` classes, the edge pipeline can:

- assign stable IDs to players/sticks during a session (tracking)
- match them against persisted local profiles (identity)
- show custom names in the overlay and include them in streamed state/events

## Performance knobs

- detector interval (N frames)
- detector input size
- max detections / NMS candidates
- stream FPS cap

