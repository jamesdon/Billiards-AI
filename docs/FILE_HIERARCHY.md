# File hierarchy (detailed)

This project is split into **edge** (Jetson Nano real-time pipeline), **core** (shared state/rules/events), and **backend** (optional offload + persistence + dashboards).

## Diagram

```text
Billiards-AI/
  docs/
    ARCHITECTURE.md                 System overview + data flow
    FILE_HIERARCHY.md               This file
    EDGE_PIPELINE.md                Edge runtime details + FPS/latency knobs
    RULES_ENGINE.md                 Rule engine interfaces and per-game rules
    EVENT_DETECTION.md              Pocket/collision/foul/shot detection logic
    CALIBRATION.md                  Homography + coordinate systems
    MODEL_OPTIMIZATION.md           ONNX/TensorRT build steps for Jetson
    DEPLOYMENT_JETSON.md            Jetson setup + systemd service + runbook
    BACKEND.md                      Optional backend API + storage + websockets
    API.md                          Message schemas + endpoints

  core/                             Shared logic (no OpenCV/YOLO dependency)
    __init__.py
    config.py                       Typed config objects
    types.py                        Dataclasses: Ball, Player, GameState, Events
    identity_store.py               Persisted player/stick profiles
    stats.py                        Stats aggregation (player/team/shot)
    geometry.py                     2D geometry helpers, transforms
    timebase.py                     Frame timestamps, dt smoothing
    event_bus.py                    Publish/subscribe for pipeline modules
    state_machine.py                Turn/inning/shot finite-state helpers
    rules/
      __init__.py
      base.py                       RuleEngine interface + common helpers
      eight_ball.py                 8-ball rules (solids/stripes, 8-ball end)
      nine_ball.py                  9-ball rules (lowest-first, win on 9)
      straight_pool.py              14.1 continuous rules (scoring, rerack)
      uk_pool.py                    UK red/yellow rules (+ black endgame)
      snooker.py                    Snooker rules (reds/colors sequence + points)

  edge/
    __init__.py
    main.py                         Edge entrypoint (camera -> overlay -> stream)
    pipeline.py                     Build/run the module graph
    io/
      __init__.py
      camera_opencv.py              OpenCV/GStreamer camera capture (Jetson CSI primary)
      video_file.py                 Replay from file
      clock.py                      Monotonic clock, fps limiter
    vision/
      __init__.py
      detector_base.py              Detector interface
      detector_onnxruntime.py        ONNXRuntime detector (Jetson-friendly)
      detector_tensorrt.py           TensorRT detector (optional)
      postprocess.py                NMS + class mapping
    tracking/
      __init__.py
      tracker_base.py               Tracker interface
      iou_tracker.py                Lightweight IoU-based tracker (baseline)
      bytetrack_like.py             ByteTrack-style association (optional)
    classify/
      __init__.py
      ball_classifier.py            Color/pattern/number heuristics (fast)
      player_stick_id.py            Appearance signatures + profile matching
      ocr_number.py                 Optional OCR (pluggable)
    calib/
      __init__.py
      table_calibration.py          Homography, pocket zones, table coords
      calib_store.py                Load/save calibration json
    events/
      __init__.py
      shot_detector.py              Shot start/stop using cue-ball accel/energy
      pocket_detector.py            Pocketing from disappearance + pocket zones
      collision_detector.py          Collision from velocity change proximity
      foul_detector.py              Scratch/no-contact/wrong-first (rule-aware)
    overlay/
      __init__.py
      draw.py                       Render IDs, trails, speeds, scoreboard
      stream_mjpeg.py               MJPEG stream server (very lightweight)
      stream_webrtc.py              WebRTC streamer (optional)
      stream_rtsp.py                RTSP publisher (optional)

  backend/                          Optional offload + history + dashboard API
    __init__.py
    app.py                          FastAPI app
    ws.py                           WebSocket broadcast of live state/events
    store.py                        SQLite storage
    models.py                       Pydantic models for API
    routes.py                       REST endpoints

  scripts/
    common.sh                       Shared env/bootstrap helpers (venv + PYTHONNOUSERSITE)
    run_phase.sh                    Entry point for phase scripts
    phase1.sh                       Environment + backend + CSI smoke checks
    phase2.sh                       Calibration validation (valid/invalid label tests)
    phase3.sh                       Detection/tracking verification sweep (n=1/2/3)
    phase4.sh                       Identity/profile persistence checks
    phase5.sh                       Foul event injection sanity checks
    phase6.sh                       Rules test execution
    phase7.sh                       Stats event injection checks
    phase8.sh                       Backend persistence checks (SQLite + optional Dynamo)
    phase9.sh                       End-to-end runtime launcher
    calib_click.py                  Interactive TL/TR/BL/BR corner picker, auto camera radios (CSI/USB), writes calibration.json
    start_calibration.sh            One-command local calibration launcher (env + guardrails + GUI)
    jetson_csi_setup.sh             Jetson camera stack triage (Argus + gst + app smoke)
    docker_jetson_build.sh          Build Jetson runtime image
    docker_jetson_up.sh             Start Jetson runtime container
    docker_jetson_down.sh           Stop Jetson runtime container

  tests/
    test_rules_8ball.py
    test_rules_9ball.py
    test_rules_snooker.py

  pyproject.toml                    Python tooling config (ruff/pytest)
  requirements.txt                  Runtime deps (edge + backend optional)
  README.md                         Quickstart
```

## “No duplicates” convention

- **All game-specific logic** lives in `core/rules/`.
- **All OpenCV/YOLO/edge-specific code** lives in `edge/`.
- **Backend is optional**; edge runs fully standalone and can emit JSON lines.

