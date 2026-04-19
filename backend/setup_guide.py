"""
Guided setup wizard: step metadata + optional persisted progress (local JSON).

Open in browser after starting the backend: GET /setup

Docs: GET /api/setup/doc?path=docs%2FTEST_PLAN.md (markdown rendered to HTML)

Optional local script launch: POST /api/setup/launch (requires SETUP_ALLOW_LAUNCH=1 and 127.0.0.1).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import markdown
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Repo root: backend/setup_guide.py -> parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PROGRESS_PATH = _PROJECT_ROOT / "data" / "setup_wizard_progress.json"
_STATIC = Path(__file__).resolve().parent / "static"

# Each checklist line: item (required), verify (how to prove it), record (what to save).
# Commands may include optional "editor_path" (repo-relative) for IDE deep links.

SETUP_STEPS: list[dict[str, Any]] = [
    {
        "id": "overview",
        "title": "Overview",
        "summary": "Billiards-AI is edge-first: detector on camera frames, rules in core, optional FastAPI backend. Work top-to-bottom or jump to any step to fix issues.",
        "checklist": [
            {
                "item": "Confirm Python 3.10+ will be used for the project venv",
                "verify": 'Run: `python3 --version` (or `which python3`). Expect 3.10 or newer.',
                "record": "Paste the version line into Notes if your environment is unusual.",
            },
            {
                "item": "Know your absolute repo path",
                "verify": "Compare the path shown in the sidebar footer with `pwd` in your terminal when `cd`’d into the repo.",
                "record": "If you use multiple clones, note which machine/path this checklist refers to.",
            },
        ],
        "commands": [],
        "links": [],
        "hints": [
            "Progress is stored in data/setup_wizard_progress.json when you click Save (or auto-saved after edits).",
            "Status lights: red = not started, yellow = in progress, green = complete.",
        ],
        "doc_refs": [{"label": "README", "path": "README.md"}, {"label": "Architecture", "path": "docs/ARCHITECTURE.md"}],
    },
    {
        "id": "environment",
        "title": "1. Environment & dependencies",
        "summary": "Create the venv and install Python dependencies. On Jetson, follow Phase 1 docs for distro OpenCV + GStreamer.",
        "checklist": [
            {
                "item": "Virtual environment exists at .venv",
                "verify": 'Run: `test -d .venv && echo OK` from the repo root. Expect `OK`.',
                "record": "If you recreated the venv, note the date and Python version in Notes.",
            },
            {
                "item": "Core dependencies install without error",
                "verify": "Run the Install command below; watch for ERROR at the end. Then run: `.venv/bin/python3 -c \"import onnxruntime,cv2; print('imports-ok')\"` (cv2 may come from pip or system on Jetson).",
                "record": "Paste the last few lines of pip output into Notes if anything was upgraded unexpectedly.",
            },
        ],
        "commands": [
            {
                "label": "Install (from repo root)",
                "command": 'cd "{project_root}" && python3 -m venv .venv && .venv/bin/python3 -m pip install -U pip && .venv/bin/python3 -m pip install -r requirements.txt',
                "editor_path": "requirements.txt",
            },
            {
                "label": "Optional: training extras",
                "command": 'cd "{project_root}" && .venv/bin/python3 -m pip install -r requirements-train.txt',
                "editor_path": "requirements-train.txt",
            },
        ],
        "links": [],
        "hints": ["Full device smoke: `bash scripts/phase1.sh` (Jetson-oriented; macOS may differ)."],
        "doc_refs": [{"label": "Phase 1 — Environment", "path": "docs/Phase 1 Environment and startup.md"}],
    },
    {
        "id": "model",
        "title": "2. Detector model (ONNX)",
        "summary": "Place exported weights as models/model.onnx and keep models/class_map.json aligned with training.",
        "checklist": [
            {
                "item": "models/model.onnx exists",
                "verify": "Run: `ls -lh models/model.onnx` from repo root. Expect a non-zero file (often ~6–15 MB).",
                "record": "Note file size and export date in Notes when you refresh the model.",
            },
            {
                "item": "class_map.json matches the ONNX output order/count",
                "verify": "Open models/class_map.json and compare indices to your training data.yaml `names:`. Count of classes must match the model head.",
                "record": "Paste a one-line summary (e.g. `0..4 ball..pockets`) in Notes after changes.",
            },
        ],
        "commands": [
            {
                "label": "Export latest train run to models/model.onnx",
                "command": 'cd "{project_root}" && bash scripts/jetson_yolo_export_latest.sh',
                "editor_path": "scripts/jetson_yolo_export_latest.sh",
            },
        ],
        "links": [],
        "hints": ["Default letterbox is 640×640; ONNX input shape must match (see detector code)."],
        "doc_refs": [{"label": "MODEL_OPTIMIZATION", "path": "docs/MODEL_OPTIMIZATION.md"}],
    },
    {
        "id": "calibration",
        "title": "3. Calibration (table + camera)",
        "summary": "Homography + pocket labels map pixels to table coordinates. Use the GUI on a desktop session (or X11-forwarded Jetson).",
        "checklist": [
            {
                "item": "calibration.json produced for this camera + table",
                "verify": "After running the calibration flow, check `ls -l calibration.json` (or your chosen path). Open the file and confirm `H` (3×3) and six `pockets` entries exist.",
                "record": "Save the file path if not the default; note table size preset used.",
            },
            {
                "item": "Pocket labels match the schema (Phase 2 style)",
                "verify": "On Jetson/Linux: `bash scripts/phase2.sh` (optional). Invalid labels should be rejected in logs.",
                "record": "Paste any Phase 2 PASS/FAIL snippet into Notes.",
            },
        ],
        "commands": [
            {
                "label": "Interactive calibration GUI",
                "command": 'cd "{project_root}" && bash scripts/start_calibration.sh',
                "editor_path": "scripts/start_calibration.sh",
            },
            {
                "label": "Headless Phase 2 checks (Jetson-oriented)",
                "command": 'cd "{project_root}" && bash scripts/phase2.sh',
                "editor_path": "scripts/phase2.sh",
            },
        ],
        "links": [
            {
                "label": "Launch calibration GUI (this Mac / device)",
                "launch": "start_calibration",
                "note": "Runs bash scripts/start_calibration.sh. Requires SETUP_ALLOW_LAUNCH=1 and localhost; grant Camera access if prompted.",
            },
            {
                "label": "Preview live table overlay (MJPEG via edge)",
                "href_template": "http://127.0.0.1:{mjpeg_port}/mjpeg",
                "note": "Start edge.main with your calibration first; set MJPEG port below (default 8080).",
            },
        ],
        "hints": ["macOS: USB camera; Jetson production: CSI. Grant Camera permission to your terminal app."],
        "doc_refs": [
            {"label": "CALIBRATION", "path": "docs/CALIBRATION.md"},
            {"label": "Phase 2", "path": "docs/Phase 2 Calibration and coordinate mapping.md"},
        ],
    },
    {
        "id": "phase3",
        "title": "4. Phase 3 — Detection & tracking",
        "summary": "Smoke-test detector + tracker. Phase 3 is headless: view output in a browser via MJPEG (not an OpenCV window).",
        "checklist": [
            {
                "item": "Automated Phase 3 script completes or manual edge run works",
                "verify": "Run `bash scripts/phase3.sh` and confirm it ends with PASS, or run the manual edge command and see no traceback.",
                "record": "Note detect_every_n and any PHASE3_USB_INDEX you used.",
            },
            {
                "item": "Overlay shows stable track IDs during motion",
                "verify": "Open the MJPEG link while the camera sees the table; move objects and confirm IDs do not flicker randomly.",
                "record": "Describe any tuning (confidence, camera) in Notes.",
            },
        ],
        "commands": [
            {
                "label": "Automated Phase 3 (macOS defaults to USB)",
                "command": 'cd "{project_root}" && source .venv/bin/activate && bash scripts/phase3.sh',
                "editor_path": "scripts/phase3.sh",
            },
            {
                "label": "Manual edge + MJPEG (example)",
                "command": 'cd "{project_root}" && .venv/bin/python3 -m edge.main --camera usb --onnx-model models/model.onnx --class-map models/class_map.json --calib calibration.json --mjpeg-port 8080',
                "editor_path": "edge/main.py",
            },
        ],
        "links": [
            {
                "label": "Open detection / tracking overlay (MJPEG)",
                "href_template": "http://127.0.0.1:{mjpeg_port}/mjpeg",
                "note": "Use the same port as --mjpeg-port (Phase 3 sweep also uses +2 / +3).",
            },
            {"label": "Health JSON (same host/port)", "href_template": "http://127.0.0.1:{mjpeg_port}/health"},
        ],
        "hints": ["CUDA provider warnings on Mac are normal; CoreML/CPU is used."],
        "doc_refs": [{"label": "Phase 3", "path": "docs/Phase 3 Detection and tracking.md"}],
    },
    {
        "id": "phase4",
        "title": "5. Phase 4 — Identity & profiles",
        "summary": "Run the backend and edge together with identities.json for persistent player/stick profiles.",
        "checklist": [
            {
                "item": "Backend responds on /health",
                "verify": "With uvicorn running: `curl -s http://127.0.0.1:8000/health` → `{\"ok\":true}` or similar.",
                "record": "Paste curl output if /health is not default.",
            },
            {
                "item": "Profiles persist across edge restarts",
                "verify": "PATCH a nickname via /profiles API (see Phase 4 doc), restart edge, confirm name still appears.",
                "record": "Note profile IDs you use for testing.",
            },
        ],
        "commands": [
            {
                "label": "Terminal A — backend",
                "command": 'cd "{project_root}" && .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000',
                "editor_path": "backend/app.py",
            },
            {
                "label": "Terminal B — edge (USB example)",
                "command": 'cd "{project_root}" && .venv/bin/python3 -m edge.main --camera usb --onnx-model models/model.onnx --class-map models/class_map.json --identities identities.json --calib calibration.json --mjpeg-port 8080',
            },
        ],
        "links": [
            {"label": "Setup wizard (this UI)", "href": "/setup"},
            {"label": "Backend health", "href": "http://127.0.0.1:8000/health"},
        ],
        "hints": ["Replace --camera usb with csi on Jetson."],
        "doc_refs": [{"label": "Phase 4", "path": "docs/Phase 4 Classification and identity.md"}],
    },
    {
        "id": "dataset_training",
        "title": "6. Dataset & training (optional)",
        "summary": "Roboflow Universe → merge → train → export. Only when refreshing the shared detector.",
        "checklist": [
            {
                "item": "ROBOFLOW_API_KEY available in the shell that downloads data",
                "verify": "Run `test -n \"$ROBOFLOW_API_KEY\" && echo set` (never paste the key into Notes).",
                "record": "Write “key configured in shell profile” or similar—no secret text.",
            },
            {
                "item": "billiards-data.yaml paths are valid on this machine",
                "verify": "Open data/datasets/billiards/billiards-data.yaml and confirm `path:` is absolute and folders exist.",
                "record": "Note dataset version or date of last merge.",
            },
        ],
        "commands": [
            {
                "label": "Universe pull + merge (example)",
                "command": 'cd "{project_root}" && export ROBOFLOW_API_KEY=… && bash scripts/universe_dataset_pipeline.sh',
                "editor_path": "scripts/universe_dataset_pipeline.sh",
            },
            {
                "label": "Train + export",
                "command": 'cd "{project_root}" && bash scripts/jetson_yolo_train.sh && bash scripts/jetson_yolo_export_latest.sh',
                "editor_path": "scripts/jetson_yolo_train.sh",
            },
        ],
        "links": [],
        "hints": ["Dedup analysis: `python3 scripts/dedup_yolo_dataset_exact.py`."],
        "doc_refs": [
            {"label": "MODEL_OPTIMIZATION", "path": "docs/MODEL_OPTIMIZATION.md"},
            {"label": "ORIN_NANO_TRAIN_AND_TEST", "path": "docs/ORIN_NANO_TRAIN_AND_TEST.md"},
        ],
    },
    {
        "id": "jetson_deploy",
        "title": "7. Jetson deployment",
        "summary": "Copy artifacts to the device, use CSI camera, optional Docker + TensorRT.",
        "checklist": [
            {
                "item": "models/ and calibration copied to the Jetson tree",
                "verify": "On device: `ls models/model.onnx models/class_map.json` and your calib path.",
                "record": "JetPack / L4T version and device hostname.",
            },
            {
                "item": "CSI camera smoke passes",
                "verify": "Run `bash scripts/jetson_csi_setup.sh` or short edge run with `--camera csi`.",
                "record": "Any flip-method or sensor-id values that worked.",
            },
        ],
        "commands": [
            {
                "label": "Docker build + up (on device)",
                "command": 'cd "{project_root}" && bash scripts/docker_jetson_build.sh && bash scripts/docker_jetson_up.sh',
                "editor_path": "scripts/docker_jetson_up.sh",
            },
        ],
        "links": [],
        "hints": ["See compose env for MODEL_PATH / CLASS_MAP_PATH."],
        "doc_refs": [{"label": "DEPLOYMENT_JETSON", "path": "docs/DEPLOYMENT_JETSON.md"}],
    },
    {
        "id": "phases_advanced",
        "title": "8. Events, rules, backend depth (Phases 5–9)",
        "summary": "Deeper integration: fouls, rules, stats, persistence, acceptance testing.",
        "checklist": [
            {
                "item": "Read TEST_PLAN gates for phases you need",
                "verify": "Open the TEST_PLAN doc in browser (link below) and skim the sections for 5–9.",
                "record": "Which phases you intend to qualify on first.",
            },
        ],
        "commands": [],
        "links": [],
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

_LAUNCH_SCRIPTS: dict[str, Path] = {
    "start_calibration": _PROJECT_ROOT / "scripts" / "start_calibration.sh",
}


def _normalize_checklist(raw: list[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            out.append(
                {
                    "item": item,
                    "verify": "Do the work described, then check this box.",
                    "record": "Add command output, version numbers, or dates in the Notes field for your future self.",
                }
            )
        elif isinstance(item, dict):
            out.append(
                {
                    "item": str(item.get("item", "")),
                    "verify": str(item.get("verify", "")),
                    "record": str(item.get("record", "")),
                }
            )
        else:
            continue
    return out


def normalized_steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for s in SETUP_STEPS:
        ns = dict(s)
        ns["checklist"] = _normalize_checklist(s.get("checklist") or [])
        steps.append(ns)
    return steps


class SetupProgress(BaseModel):
    """Persisted wizard state (local JSON, not for secrets)."""

    completed: dict[str, bool] = Field(default_factory=dict)
    checklist_done: dict[str, list[bool]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    last_step_id: str | None = None
    mjpeg_port: int = 8080


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


def _safe_doc_path(rel: str) -> Path:
    rel = rel.strip().replace("\\", "/").lstrip("/")
    if ".." in rel or rel.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not rel.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are allowed")
    if not (rel == "README.md" or rel.startswith("docs/")):
        raise HTTPException(status_code=400, detail="Path must be README.md or under docs/")
    p = (_PROJECT_ROOT / rel).resolve()
    try:
        p.relative_to(_PROJECT_ROOT.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Path escapes project root") from e
    if not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return p


def _client_localhost(request: Request) -> bool:
    host = getattr(request.client, "host", None) or ""
    return host in ("127.0.0.1", "::1", "localhost")


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
        return {
            "project_root": str(_PROJECT_ROOT),
            "launch_enabled": os.environ.get("SETUP_ALLOW_LAUNCH", "").strip() == "1",
        }

    @router.get("/api/setup/steps")
    def setup_steps() -> dict[str, Any]:
        return {"steps": normalized_steps()}

    @router.get("/api/setup/doc", response_class=HTMLResponse)
    def setup_doc(path: str) -> HTMLResponse:
        p = _safe_doc_path(path)
        text = p.read_text(encoding="utf-8")
        title = p.stem.replace("_", " ")
        body_html = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br"],
        )
        html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#0f1115;color:#e8eaed;line-height:1.55;max-width:52rem;margin:0 auto;padding:1rem 1.25rem 3rem;}}
a{{color:#4d9fff;}}
code,pre{{background:#1a1d24;padding:0.15em 0.35em;border-radius:4px;font-size:0.9em;}}
pre{{padding:0.75rem;overflow:auto;}}
pre code{{background:transparent;padding:0;}}
h1,h2,h3{{margin-top:1.4em;}}
.article{{font-size:0.95rem;}}
</style></head><body>
<p><a href="/setup">← Setup wizard</a> · <code>{path}</code></p>
<article class="article">{body_html}</article>
</body></html>"""
        return HTMLResponse(html)

    @router.post("/api/setup/launch")
    def setup_launch(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        if os.environ.get("SETUP_ALLOW_LAUNCH", "").strip() != "1":
            raise HTTPException(status_code=403, detail="Set environment SETUP_ALLOW_LAUNCH=1 to enable local script launch")
        if not _client_localhost(request):
            raise HTTPException(status_code=403, detail="Launch is only allowed from localhost")
        launch_id = str(body.get("launch") or "").strip()
        if launch_id not in _LAUNCH_SCRIPTS:
            raise HTTPException(status_code=400, detail=f"Unknown launch id: {launch_id}")
        script = _LAUNCH_SCRIPTS[launch_id]
        if not script.is_file():
            raise HTTPException(status_code=404, detail=f"Script missing: {script}")
        try:
            proc = subprocess.Popen(
                ["/bin/bash", str(script)],
                cwd=str(_PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return {"ok": True, "pid": proc.pid, "script": str(script)}

    @router.get("/api/setup/progress", response_model=SetupProgress)
    def get_progress() -> SetupProgress:
        return _load_progress()

    @router.put("/api/setup/progress", response_model=SetupProgress)
    def put_progress(body: SetupProgress) -> SetupProgress:
        _save_progress(body)
        return body

    return router
