"""
Guided setup wizard: step metadata + optional persisted progress (local JSON).

Open in browser after starting the backend: GET /setup

Docs: GET /api/setup/doc?path=docs%2FTEST_PLAN.md (markdown rendered to HTML)

Optional local script launch: POST /api/setup/launch (requires SETUP_ALLOW_LAUNCH=1 and 127.0.0.1).
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Repo root: backend/setup_guide.py -> parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Must match `TEXT_ROOT_PX` in `static/setup/index.html` and `app.js` (html root / rem base).
_TEXT_SIZE_TO_PX: dict[str, str] = {
    "small": "14px",
    "medium": "17px",
    "large": "28px",
}


def _resolve_text_size_param(text_size: str | None) -> tuple[str, str]:
    """Return (size key, font-size px) for the setup doc page <html> root."""
    c = (text_size or "").strip().lower()
    if c not in _TEXT_SIZE_TO_PX:
        c = "medium"
    return c, _TEXT_SIZE_TO_PX[c]


_TEXT_SIZE_COOKIE = "setup_text_size"


def _read_text_size_query_param(request: Request) -> str | None:
    """Read textSize= from query; tolerate any key casing (browsers/servers may vary)."""
    for key in request.query_params.keys():
        if (key or "").lower() == "textsize":
            v = (request.query_params.get(key) or "").strip().lower()
            if v in _TEXT_SIZE_TO_PX:
                return v
    return None


def _resolve_text_size_for_doc(
    text_size_q: str | None,
    cookie_value: str | None,
) -> str:
    """Order: query, cookie, medium — matches client (setup wizard) preference."""
    c = (text_size_q or "").strip().lower()
    if c in _TEXT_SIZE_TO_PX:
        return c
    k = (cookie_value or "").strip().lower()
    if k in _TEXT_SIZE_TO_PX:
        return k
    return "medium"


def _doc_viewer_href_set_text_size(path_and_query: str, size: str) -> str:
    """path_and_query like /api/setup/doc?path=docs%2Ffoo.md — ensure textSize= is set or replaced."""
    if not path_and_query.startswith("/api/setup/doc?"):
        return path_and_query
    if size not in _TEXT_SIZE_TO_PX:
        size = "medium"
    u = urlparse("http://local" + path_and_query)
    qs = parse_qs(u.query, keep_blank_values=True)
    qs["textSize"] = [size]
    pairs: list[tuple[str, str]] = []
    for key in sorted(qs.keys()):
        for v in qs[key]:
            pairs.append((key, v))
    new_q = urlencode(pairs, doseq=True)
    return f"{u.path}?{new_q}"


def _inject_text_size_into_viewer_hrefs(body_html: str, size: str) -> str:
    """Add or replace textSize= on all /api/setup/doc links in rendered HTML."""

    def repl(m: re.Match[str]) -> str:
        prefix, quote_ch, pathquery = m.group(1), m.group(2), m.group(3)
        return f"{prefix}{quote_ch}{_doc_viewer_href_set_text_size(pathquery, size)}{quote_ch}"

    return re.sub(
        r"(href=)([\"\'])(/api/setup/doc\?[^\"\'>]+)\2",
        repl,
        body_html,
    )


def _escape_ampersands_in_viewer_href_values(html: str) -> str:
    """`&` in URL query strings must be `&amp;` inside HTML `href=...` or parsers can drop the rest (Safari)."""

    def sub(m: re.Match[str]) -> str:
        q, url = m.group(1), m.group(2)
        return f"href={q}{url.replace('&', '&amp;')}{q}"

    return re.sub(
        r"\bhref=([\"'])(/api/setup/doc\?[^\"']+?)\1",
        sub,
        html,
        flags=re.IGNORECASE,
    )
_PROGRESS_PATH = _PROJECT_ROOT / "data" / "setup_wizard_progress.json"
_STATIC = Path(__file__).resolve().parent / "static"

try:
    import markdown as _markdown  # type: ignore[import-not-found]

    _HAS_MARKDOWN = True
except ImportError:
    _markdown = None  # type: ignore[assignment]
    _HAS_MARKDOWN = False


def _markdown_to_html(text: str) -> str:
    if _HAS_MARKDOWN and _markdown is not None:
        return _markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br"],
        )
    return f"<pre class=\"fallback-md\">{html.escape(text)}</pre>"


# Link bare `docs/…md` / `README.md` in list items and in <code> so rendered docs open in the setup viewer.
_LI_BARE_PATH = re.compile(
    r"<li>(docs/[^<]+\.md|README\.md)</li>",
)
_CODE_PATH = re.compile(
    r"<code>(docs/[^<]+\.md|README\.md)</code>",
)


def _linkify_viewer_doc_refs(body_html: str, text_size: str) -> str:
    """Turn plain doc path strings in rendered Markdown HTML into /api/setup/doc links (with textSize)."""
    if text_size not in _TEXT_SIZE_TO_PX:
        text_size = "medium"
    ts = quote(text_size, safe="")
    out = _LI_BARE_PATH.sub(
        lambda m: (
            f'<li><a class="md-doc-link" href="/api/setup/doc?path={quote(m.group(1), safe="")}&textSize={ts}">'
            f"{html.escape(m.group(1))}</a></li>"
        ),
        body_html,
    )
    out = _CODE_PATH.sub(
        lambda m: (
            f'<a class="md-doc-link" href="/api/setup/doc?path={quote(m.group(1), safe="")}&textSize={ts}">'
            f"<code>{html.escape(m.group(1))}</code></a>"
        ),
        out,
    )
    return out


# Each checklist line: item (required), verify (how to prove it), record (what to save).
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
                "record_paste": "python3 --version output: <paste one line here>",
            },
            {
                "item": "Know your absolute repo path",
                "verify": "This machine’s path is {project_root} (you can also copy it from the sidebar footer). It should match `pwd` in your terminal when `cd`’d into the repo.",
                "record": "If you use multiple clones, note which machine/path {project_root} refers to in your notes.",
            },
        ],
        "commands": [],
        "links": [],
        "hints": [
            "Progress is kept in the repo file data/setup_wizard_progress.json and a browser copy (localStorage); both update when you save, auto-save, or leave the page.",
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
                "verify": 'From the repository root, run: `test -d .venv && echo OK`. You should see `OK`. (If you do not, create a venv first with the “Install” command in the Commands section, then re-check this box.)',
                "record": "If you recreated the venv, note the date and Python version in Notes.",
                "record_paste": "test -d .venv: OK\ncd {project_root} && .venv/bin/python3 --version: <paste>",
            },
            {
                "item": "Core dependencies install without error",
                "verify": "Do these in order: (1) In the **Commands** section **below**, copy and run the **“Install (from repo root)”** command—wait for pip to finish and confirm there is no ERROR. (2) Then verify imports: `.venv/bin/python3 -c \"import onnxruntime,cv2; print('imports-ok')\"` (on Jetson, the OpenCV `cv2` module may be from pip or the system). Expect `imports-ok` in the output with no traceback.",
                "record": "If pip upgraded something unexpected, paste the last few lines of its output in Notes.",
                "record_paste": "import check output:\n<paste terminal lines, or write: OK / ERROR → …>",
            },
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
                "record_paste": "model.onnx: <paste one line: ls -lh output, or size + date>",
            },
            {
                "item": "class_map.json matches the ONNX output order/count",
                "verify": "Open `models/class_map.json` and compare per-class order to the names/labels in your YOLO data YAML (the dataset file you use for training). Count and ordering must match the ONNX model head and that YAML’s names list.",
                "record": "In Notes, paste a one-line note that class index order in models/class_map.json matches your YOLO names (no need to use backticks; this is free-form text, not a terminal command).",
                "record_paste": "class_map <-> YOLO data.yaml: indices 0..N in order: <e.g. ball, person, cue_stick, rack, pockets>",
            },
        ],
        "commands": [
            {
                "label": "Export latest train run to models/model.onnx",
                "command": 'cd "{project_root}" && bash scripts/jetson_yolo_export_latest.sh',
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
                "verify": "After running the calibration flow, check `ls -l calibration.json` (or your chosen path). Open the file and confirm a 3×3 homography matrix and six pocket entries are present in JSON (see CALIBRATION / Phase 2 docs for the expected structure).",
                "record": "Save the file path if not the default; note table size preset used.",
                "record_paste": "calibration path: <default or path>\ntable preset: <e.g. 7ft / 8ft / custom>\nls -l line: <paste>",
            },
            {
                "item": "Pocket labels match the schema (Phase 2 style)",
                "verify": "On Jetson/Linux: `bash scripts/phase2.sh` (optional). Invalid labels should be rejected in logs.",
                "record": "Paste any Phase 2 PASS/FAIL snippet into Notes.",
                "record_paste": "phase2.sh last lines:\n<paste PASS/FAIL lines here>",
            },
        ],
        "commands": [
            {
                "label": "Interactive calibration GUI",
                "command": 'cd "{project_root}" && bash scripts/start_calibration.sh',
            },
            {
                "label": "Headless Phase 2 checks (Jetson-oriented)",
                "command": 'cd "{project_root}" && bash scripts/phase2.sh',
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
                "record_paste": "phase3: PASS|FAIL; detect_every_n=…; PHASE3_USB_INDEX=…\n(optional) last log lines: <paste>",
            },
            {
                "item": "Overlay shows stable track IDs during motion",
                "verify": "Open the MJPEG link while the camera sees the table; move objects and confirm IDs do not flicker randomly.",
                "record": "Describe any tuning (confidence, camera) in Notes.",
                "record_paste": "Overlay check: <OK / issues>; conf_tuning=…; camera notes: …",
            },
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
                "verify": "With uvicorn running: `curl -s http://127.0.0.1:8000/health` — the response should be JSON with an ok: true (or similar) field (see Phase 4 doc for the exact contract).",
                "record": "Paste curl output if /health is not default.",
                "record_paste": "curl -s http://127.0.0.1:8000/health\n<paste body>",
            },
            {
                "item": "Profiles persist across edge restarts",
                "verify": "PATCH a nickname via /profiles API (see Phase 4 doc), restart edge, confirm name still appears.",
                "record": "Note profile IDs you use for testing.",
                "record_paste": "Profile test: id=…; nickname=…; after restart: <seen Y/N>",
            },
        ],
        "commands": [
            {
                "label": "Terminal A — backend",
                "command": 'cd "{project_root}" && .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000',
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
                "verify": "Open `data/datasets/billiards/billiards-data.yaml` and confirm the path: value is an absolute path and the image folders on disk exist.",
                "record": "Note dataset version or date of last merge.",
            },
        ],
        "commands": [
            {
                "label": "Universe pull + merge (example)",
                "command": 'cd "{project_root}" && export ROBOFLOW_API_KEY=… && bash scripts/universe_dataset_pipeline.sh',
            },
            {
                "label": "Train + export",
                "command": 'cd "{project_root}" && bash scripts/jetson_yolo_train.sh && bash scripts/jetson_yolo_export_latest.sh',
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


def _normalize_checklist(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
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
            row: dict[str, Any] = {
                "item": str(item.get("item", "")),
                "verify": str(item.get("verify", "")),
                "record": str(item.get("record", "")),
            }
            rp = item.get("record_paste")
            if isinstance(rp, str) and rp.strip():
                row["record_paste"] = rp.strip()
            out.append(row)
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
            "markdown_installed": _HAS_MARKDOWN,
        }

    @router.get("/api/setup/steps")
    def setup_steps() -> dict[str, Any]:
        return {"steps": normalized_steps()}

    @router.get("/api/setup/doc", response_class=HTMLResponse)
    def setup_doc(
        request: Request,
        path: str,
        textSize: str | None = Query(
            default=None,
            description="Text size: small, medium, or large (should match the setup wizard)",
        ),
    ) -> HTMLResponse:
        p = _safe_doc_path(path)
        text = p.read_text(encoding="utf-8")
        title = html.escape(p.stem.replace("_", " "))
        cookie_size = request.cookies.get(_TEXT_SIZE_COOKIE)
        q_text = _read_text_size_query_param(request) or textSize
        size_key = _resolve_text_size_for_doc(q_text, cookie_size)
        first_choice, _first_px = _resolve_text_size_param(size_key)
        md_html = _markdown_to_html(text)
        body_raw = _inject_text_size_into_viewer_hrefs(
            _linkify_viewer_doc_refs(md_html, first_choice), first_choice
        )
        body_html = _escape_ampersands_in_viewer_href_values(body_raw)
        warn = ""
        if not _HAS_MARKDOWN:
            warn = (
                '<p style="background:#2a1f1f;border:1px solid #5c2a2a;padding:0.65rem 0.85rem;border-radius:6px;">'
                "Install the <code>markdown</code> package for formatted docs: "
                "<code>.venv/bin/python3 -m pip install markdown</code></p>"
            )
        esc_path = html.escape(path)
        # First-paint: server uses ?textSize, then cookie, then medium (matches client).
        # Cookie + Set-Cookie keep new tabs / Safari in sync with /setup when the query is missing.
        first_choice_esc = html.escape(first_choice, quote=True)
        page = f"""<!DOCTYPE html>
<html lang="en" data-text-size="{first_choice_esc}"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<script>
(function () {{
  var LSK = "billiards-setup-text-size";
  var CKN = "setup_text_size";
  function readCookie() {{
    try {{
      var s = (document.cookie || "").split(";");
      for (var i = 0; i < s.length; i++) {{
        var p = s[i].replace(/^\\s+/, "").split("=");
        if (p[0] === CKN) {{
          var v = decodeURIComponent((p[1] || "").trim());
          if (v === "small" || v === "medium" || v === "large") return v;
        }}
      }}
    }} catch (e) {{}}
    return null;
  }}
  function hasQuerySize() {{
    try {{
      var sp = new URLSearchParams(window.location.search);
      var p = sp.get("textSize") || sp.get("textsize");
      return p === "small" || p === "medium" || p === "large" ? p : null;
    }} catch (e) {{ return null; }}
  }}
  function pickSize() {{
    var q = hasQuerySize();
    if (q) return q;
    var c = readCookie();
    if (c) return c;
    try {{
      var s = localStorage.getItem(LSK);
      if (s === "small" || s === "medium" || s === "large") return s;
    }} catch (e) {{}}
    return "medium";
  }}
  function apply(choice) {{
    document.documentElement.setAttribute("data-text-size", choice);
    try {{ localStorage.setItem(LSK, choice); }} catch (e) {{}}
    try {{
      document.cookie = CKN + "=" + encodeURIComponent(choice) + "; path=/; max-age=31536000; SameSite=Lax";
    }} catch (e) {{}}
  }}
  var choice = pickSize();
  apply(choice);
  function patchDocLinks() {{
    var c = document.documentElement.getAttribute("data-text-size") || "medium";
    document.querySelectorAll('a[href*="/api/setup/doc"]').forEach(function (a) {{
      try {{
        var u = new URL(a.href, window.location.origin);
        u.searchParams.set("textSize", c);
        a.setAttribute("href", u.pathname + (u.search ? u.search : ""));
      }} catch (e) {{}}
    }});
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", patchDocLinks);
  else patchDocLinks();
}})();
</script>
<style>
html{{box-sizing:border-box;}}
/* Root font size: must be !important + data-text-size (Safari/legacy ignore inline style + broken href query). */
html[data-text-size="small"]{{font-size:14px !important;}}
html[data-text-size="medium"]{{font-size:17px !important;}}
html[data-text-size="large"]{{font-size:28px !important;}}
html:not([data-text-size]){{font-size:17px !important;}}
body{{box-sizing:border-box;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e8eaed;line-height:1.55;max-width:52rem;margin:0 auto;padding:1rem 1.25rem 3rem;font-size:1em;}}
a{{color:#4d9fff;}}
a.md-doc-link code{{color:inherit;}}
/* em — from <html> (same rem scale as /setup) */
code,pre{{background:#1a1d24;padding:0.15em 0.35em;border-radius:4px;font-size:0.95em;}}
pre{{padding:0.75rem;overflow:auto;}}
pre code{{background:transparent;padding:0;font-size:inherit;}}
h1{{font-size:1.6em;}}
h2{{font-size:1.3em;}}
h3{{font-size:1.1em;}}
h1,h2,h3{{margin-top:1.4em;}}
p,li,td,th{{font-size:1em;}}
</style></head><body>
<p><a href="/setup">← Setup wizard</a> · <code>{esc_path}</code></p>
{warn}
<article class="article">{body_html}</article>
</body></html>"""
        resp = HTMLResponse(page)
        if first_choice in _TEXT_SIZE_TO_PX:
            resp.set_cookie(
                _TEXT_SIZE_COOKIE,
                first_choice,
                max_age=31536000,
                path="/",
                samesite="lax",
            )
        return resp

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
