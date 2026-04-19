"""
Guided setup wizard: step metadata + optional persisted progress (local JSON).

Open in browser after starting the backend: GET /setup
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Repo root: backend/setup_guide.py -> parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROGRESS_PATH = _PROJECT_ROOT / "data" / "setup_wizard_progress.json"
_STATIC = Path(__file__).resolve().parent / "static"

SETUP_STEPS: list[dict[str, Any]] = [
    {
        "id": "overview",
        "title": "Overview",
        "summary": "Billiards-AI is edge-first: detector on camera frames, rules in core, optional FastAPI backend. Use this guide in order or jump to any step to fix or redo work.",
        "checklist": [
            "Python 3.10+ venv at .venv (see README)",
            "You know your repo path (shown in commands as PROJECT_ROOT)",
        ],
        "commands": [],
        "hints": [
            "Progress (checkboxes and notes) is saved in data/setup_wizard_progress.json when you use Save.",
        ],
        "doc_refs": [{"label": "README", "path": "README.md"}, {"label": "Architecture", "path": "docs/ARCHITECTURE.md"}],
    },
    {
        "id": "environment",
        "title": "1. Environment & dependencies",
        "summary": "Create the venv and install requirements (Phase 1 style smoke). On Jetson use distro OpenCV + GStreamer per docs.",
        "checklist": [
            "Virtualenv activated",
            "pip install -r requirements.txt succeeded",
        ],
        "commands": [
            {
                "label": "Install (from repo root)",
                "command": 'cd "{project_root}" && python3 -m venv .venv && .venv/bin/python3 -m pip install -U pip && .venv/bin/python3 -m pip install -r requirements.txt',
            },
            {
                "label": "Optional: training extras",
                "command": 'cd "{project_root}" && .venv/bin/python3 -m pip install -r requirements-train.txt',
            },
        ],
        "hints": ["For full Phase 1 script on device: bash scripts/phase1.sh"],
        "doc_refs": [{"label": "Phase 1", "path": "docs/Phase 1 Environment and startup.md"}],
    },
    {
        "id": "model",
        "title": "2. Detector model (ONNX)",
        "summary": "Place exported weights and keep class_map.json aligned with training names/indices.",
        "checklist": [
            "models/model.onnx present (gitignored; copy or export)",
            "models/class_map.json matches ONNX outputs (e.g. ball, person, cue_stick, rack, pockets)",
        ],
        "commands": [
            {
                "label": "Export example (after training)",
                "command": 'cd "{project_root}" && bash scripts/jetson_yolo_export_latest.sh',
            },
        ],
        "hints": [
            "Letterbox size must match export (default 640×640); see edge vision detector config.",
        ],
        "doc_refs": [{"label": "MODEL_OPTIMIZATION", "path": "docs/MODEL_OPTIMIZATION.md"}],
    },
    {
        "id": "calibration",
        "title": "3. Calibration (table + camera)",
        "summary": "Homography and pocket labels map image pixels to table coordinates. Required for accurate rules/overlay on the real table.",
        "checklist": [
            "calibration.json exists beside the repo or path you pass to edge.main",
            "Six pocket labels validated (Phase 2 invalid-label checks pass on device)",
        ],
        "commands": [
            {
                "label": "Interactive GUI (desktop / forwarded X11 on Jetson)",
                "command": 'cd "{project_root}" && bash scripts/start_calibration.sh',
            },
            {
                "label": "Headless Phase 2 checks (Jetson-oriented)",
                "command": 'cd "{project_root}" && bash scripts/phase2.sh',
            },
        ],
        "hints": ["macOS: use USB camera flags; Jetson production uses --camera csi."],
        "doc_refs": [
            {"label": "CALIBRATION", "path": "docs/CALIBRATION.md"},
            {"label": "Phase 2", "path": "docs/Phase 2 Calibration and coordinate mapping.md"},
        ],
    },
    {
        "id": "phase3",
        "title": "4. Phase 3 — Detection & tracking",
        "summary": "Smoke-test detector + tracker. Script is headless: open the MJPEG URL in a browser (no OpenCV window).",
        "checklist": [
            "scripts/phase3.sh completes or manual edge.main run works",
            "Track IDs stable in browser overlay; tune detect_every_n if needed",
        ],
        "commands": [
            {
                "label": "Automated Phase 3 (macOS defaults to USB)",
                "command": 'cd "{project_root}" && source .venv/bin/activate && bash scripts/phase3.sh',
            },
            {
                "label": "Manual edge + MJPEG (example)",
                "command": 'cd "{project_root}" && .venv/bin/python3 -m edge.main --camera usb --onnx-model models/model.onnx --class-map models/class_map.json --calib calibration.json --mjpeg-port 8080',
            },
        ],
        "hints": [
            "View stream: http://127.0.0.1:8080/mjpeg (ports 8082/8083 for later segments of phase3.sh).",
            "macOS: grant Camera to Terminal/Cursor; PHASE3_USB_INDEX=1 if wrong device.",
        ],
        "doc_refs": [{"label": "Phase 3", "path": "docs/Phase 3 Detection and tracking.md"}],
    },
    {
        "id": "phase4",
        "title": "5. Phase 4 — Identity & profiles",
        "summary": "Backend serves player/stick profiles; edge loads identities.json for persistent nicknames.",
        "checklist": [
            "Backend /health OK",
            "edge.main run with --identities; PATCH /profiles updates persist",
        ],
        "commands": [
            {
                "label": "Terminal A — backend",
                "command": 'cd "{project_root}" && .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000',
            },
            {
                "label": "Terminal B — edge (adjust camera)",
                "command": 'cd "{project_root}" && .venv/bin/python3 -m edge.main --camera usb --onnx-model models/model.onnx --class-map models/class_map.json --identities identities.json --calib calibration.json --mjpeg-port 8080',
            },
        ],
        "hints": ["See docs/Phase 4 for curl examples against /profiles."],
        "doc_refs": [{"label": "Phase 4", "path": "docs/Phase 4 Classification and identity.md"}],
    },
    {
        "id": "dataset_training",
        "title": "6. Dataset & training (optional)",
        "summary": "Refresh or build YOLO data from Roboflow Universe, merge, train, export to models/model.onnx.",
        "checklist": [
            "ROBOFLOW_API_KEY set for downloads",
            "data/datasets/billiards layout and billiards-data.yaml paths correct",
        ],
        "commands": [
            {
                "label": "Full Universe pull + merge (example)",
                "command": 'cd "{project_root}" && export ROBOFLOW_API_KEY=… && bash scripts/universe_dataset_pipeline.sh',
            },
            {
                "label": "Train + export",
                "command": 'cd "{project_root}" && bash scripts/jetson_yolo_train.sh && bash scripts/jetson_yolo_export_latest.sh',
            },
        ],
        "hints": ["Exact dedup analysis: python3 scripts/dedup_yolo_dataset_exact.py"],
        "doc_refs": [{"label": "MODEL_OPTIMIZATION", "path": "docs/MODEL_OPTIMIZATION.md"}, {"label": "Orin train/test", "path": "docs/ORIN_NANO_TRAIN_AND_TEST.md"}],
    },
    {
        "id": "jetson_deploy",
        "title": "7. Jetson deployment",
        "summary": "Production target: Orin Nano, CSI camera, Docker optional, TensorRT optional.",
        "checklist": [
            "models/ and calibration on device",
            "CSI smoke: scripts/jetson_csi_setup.sh or jetson_edge_smoke_csi.sh",
        ],
        "commands": [
            {
                "label": "Docker build/up (on device)",
                "command": 'cd "{project_root}" && bash scripts/docker_jetson_build.sh && bash scripts/docker_jetson_up.sh',
            },
        ],
        "hints": ["Compose mounts ./models and uses MODEL_PATH / CLASS_MAP_PATH env overrides."],
        "doc_refs": [{"label": "DEPLOYMENT_JETSON", "path": "docs/DEPLOYMENT_JETSON.md"}],
    },
    {
        "id": "phases_advanced",
        "title": "8. Events, rules, backend depth (Phases 5–9)",
        "summary": "Event/foul detection, rules engine, stats, persistence, end-to-end acceptance — see TEST_PLAN.",
        "checklist": [],
        "commands": [],
        "hints": [
            "Phase 5: shot/collision/pocket/foul detectors",
            "Phase 6: end-of-game rules",
            "Phases 7–8: stats + backend",
            "Phase 9: acceptance",
        ],
        "doc_refs": [
            {"label": "TEST_PLAN", "path": "docs/TEST_PLAN.md"},
            {"label": "EVENT_DETECTION", "path": "docs/EVENT_DETECTION.md"},
            {"label": "Phase 9", "path": "docs/Phase 9 End-to-end acceptance.md"},
        ],
    },
]


class SetupProgress(BaseModel):
    """Persisted wizard state (local JSON, not for secrets)."""

    completed: dict[str, bool] = Field(default_factory=dict)
    # step_id -> checked state for each checklist line (same order as SETUP_STEPS)
    checklist_done: dict[str, list[bool]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    last_step_id: str | None = None


def _load_progress() -> SetupProgress:
    if not _PROGRESS_PATH.is_file():
        return SetupProgress()
    try:
        raw = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
        return SetupProgress.model_validate(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        return SetupProgress()


def _save_progress(p: SetupProgress) -> None:
    _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROGRESS_PATH.write_text(p.model_dump_json(indent=2), encoding="utf-8")


def build_router() -> APIRouter:
    router = APIRouter(tags=["setup"])

    @router.get("/setup", response_class=HTMLResponse, include_in_schema=True)
    def setup_page() -> HTMLResponse:
        html_path = _STATIC / "setup" / "index.html"
        if not html_path.is_file():
            return HTMLResponse("<h1>Setup UI missing</h1><p>Rebuild repo; expected backend/static/setup/index.html</p>", status_code=500)
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @router.get("/api/setup/context")
    def setup_context() -> dict[str, Any]:
        return {"project_root": str(_PROJECT_ROOT)}

    @router.get("/api/setup/steps")
    def setup_steps() -> dict[str, Any]:
        return {"steps": SETUP_STEPS}

    @router.get("/api/setup/progress", response_model=SetupProgress)
    def get_progress() -> SetupProgress:
        return _load_progress()

    @router.put("/api/setup/progress", response_model=SetupProgress)
    def put_progress(body: SetupProgress) -> SetupProgress:
        _save_progress(body)
        return body

    return router
