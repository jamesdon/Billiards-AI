# File hierarchy (detailed)

This project is split into **edge** (Jetson Orin Nano real-time pipeline, JetPack 5.x), **core** (shared state/rules/events), and **backend** (optional offload + persistence + dashboards).

## Diagram

```text
Billiards-AI/
  docs/
    ARCHITECTURE.md                 System overview + data flow
    FEATURE_TRAJECTORY_PREDICTION.md  Trajectory assist module (isolated from rules)
    FEATURE_REALTIME_RULES.md       Rules engine contract (isolated from trajectory)
    FEATURE_VOICE_OVERLAYS_PROJECTOR.md  Voice (EN first), projector layers, projector homography notes
    FEATURE_GAME_PHASE_VISION.md    Vision-derived match phase (rack/balls/shot)
    HARDWARE_IMX477_AUDIO.md        IMX477 + low-distortion lens; microphone fouls roadmap
    FILE_HIERARCHY.md               This file
    EDGE_PIPELINE.md                Edge runtime details + FPS/latency knobs
    RULES_ENGINE.md                 Rule engine interfaces and per-game rules
    EVENT_DETECTION.md              Pocket/collision/foul/shot detection logic
    CALIBRATION.md                  Homography + coordinate systems
    MODEL_OPTIMIZATION.md           Optional one-time train/tune + ONNX export; normal devices reuse the same model; ONNX→TensorRT on Orin-class Jetson
    ORIN_NANO_TRAIN_AND_TEST.md     On-device YOLO train + env guardrails + pytest + phase scripts (`/home/$USER/Billiards-AI`); Jetson Orin Nano / JetPack 5.x
    JETSON_NANO_TRAIN_AND_TEST.md   Bookmark alias → see ORIN_NANO_TRAIN_AND_TEST.md
    DEPLOYMENT_JETSON.md            Orin Nano (JetPack 5.x) setup + systemd service + runbook
    BACKEND.md                      Optional backend API + storage + websockets
    API.md                          Message schemas + endpoints

  models/                           Single location for detector runtime + training contract
    class_map.json                  Maps ONNX class index → pipeline label (`ball`, `person`, `cue_stick`, `rack`, `pockets`); committed
    model.onnx                      Exported detector weights (not in git; copy or export here)

  core/                             Shared logic (no OpenCV/YOLO dependency)
    overlay_state.py              Projector layer toggles + highlight labels (voice-driven)
    __init__.py
    config.py                       Typed config objects
    types.py                        Dataclasses: Ball, Player, GameState, Events
    identity_store.py               Persisted player/stick profiles
    stats.py                        Stats aggregation (player/team/shot + achievements)
    geometry.py                     2D geometry helpers, transforms
    timebase.py                     Frame timestamps, dt smoothing
    event_bus.py                    Publish/subscribe for pipeline modules
    state_machine.py                Turn/inning/shot finite-state helpers
    rules/
      __init__.py
      base.py                       RuleEngine interface + common helpers
      turn_events.py                player_turn_begin / player_turn_over helpers (turn vs single shot)
      eight_ball.py                 8-ball rules (solids/stripes, 8-ball end)
      nine_ball.py                  9-ball rules (lowest-first, win on 9)
      straight_pool.py              14.1 continuous rules (scoring, rerack)
      uk_pool.py                    UK red/yellow rules (+ black endgame)
      snooker.py                    Snooker rules (reds/colors sequence + points)

  edge/
    __init__.py
    main.py                         Edge entrypoint (MJPEG binds right after CLI parse; calibration load; optional `--voice-line` / `--voice-phrases-file` / `--enable-audio-micro-foul`; camera -> overlay -> stream)
    pipeline.py                     Build/run the module graph; wires trajectory assist, vision phase, shot-hint stubs, optional micro-foul detector
    io/
      __init__.py
      camera_opencv.py              OpenCV/GStreamer camera capture (NVIDIA CSI primary on Jetson); raises if capture opens but returns no frames
      video_file.py                 Replay from file
      clock.py                      Monotonic clock, fps limiter
    vision/
      __init__.py
      detector_base.py              Detector interface
      detector_onnxruntime.py        ONNXRuntime detector (portable baseline; Jetson GPU EP when installed)
      detector_tensorrt.py           TensorRT detector (optional)
      postprocess.py                NMS + class mapping
    tracking/
      __init__.py
      tracker_base.py               Tracker interface
      iou_tracker.py                IoU tracker + constant-velocity bbox prediction + center-distance fallback for fast motion
      bytetrack_like.py             ByteTrack-style association (optional)
    classify/
      __init__.py
      ball_classifier.py            Color/pattern/number heuristics (fast)
      player_stick_id.py            Appearance signatures + profile matching
      ocr_number.py                 Optional OCR (pluggable)
    assist/
      __init__.py
      shot_hints.py                 Stub “best / alt” aim polylines in table meters (replace with solver)
    calib/
      __init__.py
      table_geometry.py             Homography from 4 outside corners + default pockets/kitchen geometry
      table_layout.py               Kitchen/break polygons; infer table size from pocket labels
      calib_store.py                Load/save calibration json (H camera, optional H_projector table→projector px, pockets, table size, kitchen/break polygons)
    events/
      __init__.py
      shot_detector.py              Shot start/stop: cue-ball |Δv|/dt threshold (m/s²); rest-speed shot end
      thread_the_needle.py          Tight-clearance heuristic → ACHIEVEMENT (thread_the_needle)
      pocket_detector.py            Pocketing from disappearance + pocket zones
      collision_detector.py          Collision from velocity change proximity
      foul_detector.py              Scratch/no-contact/wrong-first (rule-aware)
      micro_foul_audio.py           Micro-foul audio correlation stub (double-hit/push TBD; optional `SHOT_START` windowing)
    overlay/
      __init__.py
      draw.py                       Render IDs, trails, scoreboard; camera projector-layer preview + optional top-right **projector inset** when `H_projector` is set (mirrors break box/string, hints, trajectory)
      stream_mjpeg.py               MJPEG stream server (GET /health, /mjpeg; threaded server so /mjpeg cannot block /health; SO_REUSEADDR)
      stream_webrtc.py              WebRTC streamer (optional)
      stream_rtsp.py                RTSP publisher (optional)
    voice/
      intents_en.py                 English phrase → intent; applies to GameState.projector_layers
    trajectory/
      assist.py                     Cue path history + stub projection (no rules coupling)
    audio/
      capture.py                    Thread-safe PCM chunk ring buffer for micro-foul audio fusion
      mic_stream.py                 Optional `sounddevice` capture → ring buffer (`requirements-audio.txt`)
    game_phase.py                   VisionGamePhase estimator (rack/ball/shot heuristics)

  backend/                          Optional offload + history + dashboard API
    __init__.py
    app.py                          FastAPI app (`/event`, `/state`, `/live/state`, WebSocket hub)
    reducer.py                      LiveGameReducer: merges snapshots + shot/pocket/collision/rail/foul events for `GET /live/state`
    ws.py                           WebSocket broadcast of live state/events
    store.py                        SQLite storage
    aws_store.py                    Optional DynamoDB shot/stick stats
    fouls.py                        Manual foul injection helper
    profiles.py                     Profile routes
    models.py                       Pydantic models for API
    routes.py                       REST endpoints

  scripts/
    common.sh                       Shared env/bootstrap helpers (venv + PYTHONNOUSERSITE)
    run_phase.sh                    Entry point for phase scripts
    phase1.sh                       Environment + backend + CSI smoke checks
    phase2.sh                       Headless calibration validation (no GUI); valid-calibration MJPEG smoke uses `PHASE2_CAMERA` (default `csi`, or `usb` / numeric V4L index) plus `CSI_*` / `PHASE2_USB_INDEX`; picks a free localhost MJPEG port in 18080–18255 when `MJPEG_PORT` is unset
    phase3.sh                       Detection/tracking verification sweep (n=1/2/3)
    phase4.sh                       Identity/profile persistence checks
    phase5.sh                       Foul event injection sanity checks
    phase6.sh                       Rules test execution
    phase7.sh                       Stats event injection checks
    phase8.sh                       Backend persistence checks (SQLite + optional Dynamo)
    phase9.sh                       End-to-end runtime launcher
    bootstrap_billiards_dataset.sh  YOLO dataset dirs + billiards-data.yaml with expanded absolute path
    jetson_train_env.sh             Orin Nano: git pull + venv + requirements + requirements-train
    jetson_prepare_yolo_dataset.sh  Orin Nano: chmod + run bootstrap + grep path line
    jetson_yolo_train.sh            Ultralytics train (Apple Silicon: higher default epochs/batch/workers; Jetson/Linux: conservative; env overrides); exits early if `data/datasets/billiards/images/train` has no JPEG/PNG
    jetson_yolo_export_latest.sh    Orin Nano: export newest best.pt to models/model.onnx
    jetson_pytest.sh                Orin Nano: pytest tests/
    jetson_phases_1_3.sh            Orin Nano: run_phase 1 then 3
    jetson_edge_smoke_csi.sh        Orin Nano: edge.main CSI smoke (until Ctrl+C)
    JETSON_ONE_LINERS.txt           Plain-text paste list for bash (no Markdown fences)
    jetson_capture_training_frames.sh  Wrapper: live CSI → JPEGs for YOLO labeling
    capture_csi_training_frames.py     Saves frames from CSI (same pipeline as edge.main)
    roboflow_universe_manifest.example.yaml  Template for batch Universe downloads (copy to `roboflow_universe_manifest.yaml`, gitignored)
    roboflow_universe_pull.py       Batch-download Roboflow Universe YOLOv8 exports from a manifest (`ROBOFLOW_API_KEY` env)
    yolo_import_class_report.py    Scan `_imports/...` (or given paths): per-class box counts, parseable `names:` from `data.yaml`, heuristic hints → Billiards-AI class ids
    merge_yolo_imports_to_billiards.py  Merge Roboflow imports into `data/datasets/billiards/` (prefixed stems; `--map-json`, `--only-source-ids`, or `--batch-yaml` + auto remap)
    dedup_yolo_dataset_exact.py     SHA-256 duplicate + train/val overlap analysis for `images/{train,val}`; no deletes
    roboflow_merge_batch.example.yaml  Example batch merge config (copy to `roboflow_merge_batch.yaml`) for many Universe exports at once
    universe_dataset_pipeline.sh    One-shot: `jetson_prepare_yolo_dataset.sh` + `roboflow_universe_pull.py` + `merge_yolo_imports_to_billiards.py` (uses `*.yaml` if present, else `*.example.yaml`)
    calib_click.py                  Interactive calibration: TL/TR/BL/BR at corner-pocket **inner throat**; `_estimate_outside_corners` avoids picking the **largest** hull quad (often the room outline) by scoring quads in an area band and with border inset; `_order_physical_table_corners` tries both kitchen-at-top vs kitchen-at-bottom hypotheses vs image-axis order; Hough + `_pocket_throat_from_seed`; `warpAffine` + `BORDER_CONSTANT` for pan/zoom voids; writes calibration.json; CLI via start_calibration.sh
    start_calibration.sh            One-command calibration launcher (venv + NumPy/OpenCV ABI guard on **venv python** including GStreamer=YES for CSI + GUI); forwards extra CLI args to calib_click (e.g. --width 640 --camera 0); env overrides for CSI/USB; asserts stable view-control hooks in calib_click.py
    jetson_csi_setup.sh             Jetson-family CSI triage: tolerant `apt-get update`, v4l-utils + gst tools, Argus restart, device list, gst smoke, edge.main probe
    docker_jetson_build.sh          Build Jetson runtime image
    docker_jetson_up.sh             Start Jetson runtime container
    docker_jetson_down.sh           Stop Jetson runtime container

  tests/
    test_rules_8ball.py
    test_rules_9ball.py
    test_rules_snooker.py

  pyproject.toml                    Python tooling config (ruff/pytest)
  requirements.txt                  Runtime deps (edge + backend optional)
  requirements-audio.txt            Optional `sounddevice` + PortAudio for `--mic-device` live capture
  requirements-train.txt              Optional Ultralytics stack; pin numpy<2 for stable OpenCV/Ultralytics ABI on Jetson-family devices
  README.md                         Quickstart
```

## “No duplicates” convention

- **All game-specific logic** lives in `core/rules/`.
- **All OpenCV/YOLO/edge-specific code** lives in `edge/`.
- **Backend is optional**; edge runs fully standalone and can emit JSON lines.

