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
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

# Repo root: backend/setup_guide.py -> parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# FastAPI + setup guide HTTP port (run_backend.sh, Dockerfile). See docs/PORTS.md.
DEFAULT_API_PORT: int = 8000
DEFAULT_MJPEG_PORT: int = 8001


def _api_port_from_request(request: Request) -> int:
    h = (request.headers.get("host") or "").strip()
    if h and ":" in h:
        try:
            p = int(h.rsplit(":", 1)[-1])
            if 1 <= p <= 65535:
                return p
        except ValueError:
            pass
    p = request.url.port
    if p is not None and 1 <= p <= 65535:
        return int(p)
    try:
        return int((os.environ.get("BACKEND_PORT") or str(DEFAULT_API_PORT)).strip())
    except ValueError:
        return DEFAULT_API_PORT

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
                "verify": "Run `python3 --version` (or `which python3`). Expect Python 3.10 or newer.",
                "record": "If the version is odd for your team, put the one line of output in Notes.",
            },
            {
                "item": "Know your absolute repo path",
                "verify": "The repo on this machine is {project_root} (see the sidebar on this page). In a terminal, `cd` to the repo and run `pwd` — the path should match.",
                "record": "If you have several clones, note in Notes which machine this path refers to.",
            },
        ],
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
                "verify": "From the repository root, run `test -d .venv && echo OK`. You should see `OK`. If not, run step 1) of the next checklist line (core dependencies install) first, then re-check this box.",
                "record": "If you rebuilt the venv, note the date and `.venv` Python version in Notes.",
            },
            {
                "item": "Core dependencies install without error",
                "verify": (
                    "1) At the repository root, run this one-line install. Wait for pip to finish. "
                    "A pip line marked ERROR is a failure; most warnings are OK.\n"
                    '`cd "{project_root}" && python3 -m venv .venv && .venv/bin/python3 -m pip install -U pip && .venv/bin/python3 -m pip install -r requirements.txt`\n\n'
                    "2) Confirm onnxruntime and OpenCV (cv2) import (Jetson may use system cv2; that is fine if this command succeeds; expect a single line of output, no Python traceback).\n"
                    r"""`.venv/bin/python3 -c "import onnxruntime,cv2; print('imports-ok')"`"""
                    + "\n\n"
                    "3) Optional — only if you need training tools on this machine, install training extras in the same venv.\n"
                    '`cd "{project_root}" && .venv/bin/python3 -m pip install -r requirements-train.txt`'
                ),
                "record": "If pip or the import check failed, paste the last error lines in Notes. If a package upgrade was unexpected, name it in Notes.",
            },
        ],
        "links": [],
        "hints": [
            "Optional (Jetson with CSI only): with the venv active, from the repository root run `bash scripts/phase1.sh`. That script installs Python deps, checks that OpenCV was built with GStreamer (needed for CSI), runs compileall, ruff, pytest, then smoke-tests the backend and edge with `--camera csi`. It is not a generic desktop check—do not expect it to succeed on macOS or on a system without a CSI camera and a GStreamer-capable OpenCV; use the Environment checklist on those machines instead."
        ],
        "doc_refs": [{"label": "Phase 1 — Environment", "path": "docs/Phase 1 Environment and startup.md"}],
    },
    {
        "id": "model",
        "title": "2. Detector model (ONNX)",
        "summary": "Use ONNX exported from this repo’s latest training run (same runs/ tree) at models/model.onnx, with models/class_map.json matching that training.",
        "checklist": [
            {
                "item": "models/model.onnx exists",
                "verify": (
                    "1) Export the newest trained weights from this same repository clone. The script "
                    "jetson_yolo_export_latest.sh selects the latest runs/detect/.../weights/best.pt, "
                    "runs the Ultralytics ONNX export, and copies the file to models/model.onnx. From the repository root run:\n"
                    '`cd "{project_root}" && bash scripts/jetson_yolo_export_latest.sh`'
                    "\n\n"
                    "If you must bring an ONNX from another machine, install it in this tree as models/model.onnx only when its class head still matches models/class_map.json and your YOLO data YAML; when in doubt, train or re-export in this clone so the run, class map, and YAML stay one consistent line.\n\n"
                    "2) Confirm the file on disk (typical size is a few to tens of MB):\n"
                    "`ls -lh models/model.onnx`"
                ),
                "record": "When you replace the model, put size or the `ls -lh` line and the date in Notes if useful.",
            },
            {
                "item": "class_map.json matches the ONNX output order/count",
                "verify": "From the repo root, run `more models/class_map.json` (or open that path in an editor) and compare per-class order to the names in your YOLO `data` YAML. Class count and order must match the ONNX head and that YAML’s `names` list.",
                "record": "If the mapping is non-obvious, add a short free-form line in Notes (e.g. index order vs names).",
            },
        ],
        "links": [],
        "hints": ["Default letterbox is 640×640; ONNX input shape must match (see detector code)."],
        "doc_refs": [{"label": "MODEL_OPTIMIZATION", "path": "docs/MODEL_OPTIMIZATION.md"}],
    },
    {
        "id": "calibration",
        "title": "3. Calibration (table + camera)",
        "summary": "Homography + pocket labels map pixels to table coordinates. On macOS, the starter script uses a USB camera by default; Jetson uses CSI. Use the GUI on a desktop session (or X11-forwarded Jetson).",
        "checklist": [
            {
                "item": "calibration.json produced for this camera + table",
                "verify": (
                    "1) From the repository root, start the interactive calibration flow (GUI; needs a desktop or forwarded display on Jetson):\n"
                    '`cd "{project_root}" && bash scripts/start_calibration.sh`'
                    "\n\n2) Confirm your output file and inspect JSON for a 3×3 homography and six pockets (see CALIBRATION / Phase 2 docs for structure). Example for the default file name:\n"
                    "`ls -l calibration.json`"
                ),
                "record": "If the path is not the default, or you used a table preset, put that in Notes.",
            },
            {
                "item": "Pocket labels match the schema (Phase 2 style)",
                "verify": (
                    "On Jetson or Linux, optional automated checks (invalid labels should show in logs):\n"
                    '`cd "{project_root}" && bash scripts/phase2.sh`'
                ),
                "record": "If you ran `phase2.sh` and the log matters, paste the PASS/FAIL lines in Notes.",
            },
        ],
        "links": [
            {
                "label": "Launch calibration GUI (this Mac / device)",
                "launch": "start_calibration",
                "note": "Runs scripts/start_calibration.sh (USB on macOS by default, CSI on Linux). Requires SETUP_ALLOW_LAUNCH=1 and localhost; allow Camera for your terminal app.",
            },
            {
                "label": "Preview live table overlay (MJPEG via edge)",
                "href_template": "http://127.0.0.1:{mjpeg_port}/mjpeg",
                "note": "Start edge.main with your calibration first; set MJPEG port below (default 8001, docs/PORTS.md).",
            },
        ],
        "hints": [
            "macOS: `start_calibration.sh` defaults to a USB camera and only requires venv + NumPy<2 + `import cv2` (pip opencv, no GStreamer). Jetson: CSI + GStreamer-backed OpenCV for production. Grant Camera to Terminal / iTerm / VS Code."
        ],
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
                "verify": (
                    "1) Automated (macOS USB defaults; on Jetson set `PHASE3_USB_INDEX` if the script needs it). From the repo root:\n"
                    '`cd "{project_root}" && source .venv/bin/activate && bash scripts/phase3.sh`'
                    "\nExpect a PASS line, or at least no Python traceback on the run you care about. "
                    "If startup looks hung after a Starting line, wait for ONNX and the camera, or in another terminal follow the n2 log. The `tail` line below includes a Copy button:\n"
                    '`tail -f "{project_root}/.phase3_n2.log"`'
                    "\n\n2) Or run edge + MJPEG by hand (use `--camera csi` on Jetson instead of `usb` when appropriate; `--mjpeg-port` must match the sidebar and buttons on this page):\n"
                    '`cd "{project_root}" && .venv/bin/python3 -m edge.main --camera usb --onnx-model models/model.onnx --class-map models/class_map.json --calib calibration.json --mjpeg-port {mjpeg_port}`'
                ),
                "record": "If you had to set `PHASE3_USB_INDEX` or `detect_every_n`, note values in Notes.",
            },
            {
                "item": "Overlay shows stable track IDs during motion",
                "verify": (
                    "Set the MJPEG port in the left sidebar to the same value your running edge process uses for its MJPEG port "
                    "(the --mjpeg-port flag). "
                    "Use the two buttons in this same checklist item (no separate Quick links section for this) to open the live "
                    "video and the JSON /health check. With the camera on the table, move objects: track IDs "
                    "should not flicker at random."
                ),
                "verify_actions": [
                    {
                        "label": "Open MJPEG overlay",
                        "href_template": "http://127.0.0.1:{mjpeg_port}/mjpeg",
                    },
                    {
                        "label": "Open edge /health",
                        "href_template": "http://127.0.0.1:{mjpeg_port}/health",
                    },
                ],
                "record": "If you change confidence, camera, or port, a short line in Notes helps later.",
            },
        ],
        "links": [],
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
                "verify": (
                    "1) Start the API in a separate terminal (this guide’s default is port {api_port} — set `BACKEND_PORT` in "
                    "`run_backend.sh` or the environment to change it; it must match the port in your browser’s URL for this page):\n"
                    '`cd "{project_root}" && .venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port {api_port}`'
                    "\n\n2) When it is up:\n"
                    "`curl -s http://127.0.0.1:{api_port}/health`"
                    "\nExpect JSON with an ok field (see Phase 4 doc for the exact response)."
                ),
                "record": "If `/health` is not what you expect, paste the `curl` body in Notes.",
            },
            {
                "item": "Profiles persist across edge restarts",
                "verify": (
                    "1) With edge in the loop, use a USB or CSI run as you prefer (example USB):\n"
                    '`cd "{project_root}" && .venv/bin/python3 -m edge.main --camera usb --onnx-model models/model.onnx --class-map models/class_map.json --identities identities.json --calib calibration.json --mjpeg-port {mjpeg_port}`'
                    "\n\n2) `PATCH` a nickname through `/profiles` (see Phase 4 doc), restart edge, and confirm the name returns after restart."
                ),
                "record": "Note a profile id you used for this test, if you want a paper trail.",
            },
        ],
        "links": [
            {"label": "Setup wizard (this UI)", "href": "/setup"},
            {"label": "Backend health", "href_template": "http://127.0.0.1:{api_port}/health"},
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
                "verify": (
                    "1) In the shell you will use for downloads, run `test -n \"$ROBOFLOW_API_KEY\" && echo set` (never paste the key into Notes).\n\n"
                    "2) To pull a Universe sample and merge, on the same machine, from the repository root, set the key in that shell and run:\n"
                    '`cd "{project_root}" && export ROBOFLOW_API_KEY=… && bash scripts/universe_dataset_pipeline.sh`'
                    "\n(Replace `…` with your key or rely on the variable already in the environment.)"
                ),
                "record": "A note like “key is in my shell profile” is enough. Do not store the secret in Notes.",
            },
            {
                "item": "billiards-data.yaml paths are valid on this machine",
                "verify": (
                    "1) Open `data/datasets/billiards/billiards-data.yaml` and check that the dataset `path` points at real directories on this machine.\n\n"
                    "2) To train and export a model on this machine (after the environment step), from the repository root:\n"
                    '`cd "{project_root}" && bash scripts/jetson_yolo_train.sh && bash scripts/jetson_yolo_export_latest.sh`'
                ),
                "record": "If you care about traceability, put dataset or merge date in Notes.",
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
                "verify": (
                    "On the device, confirm weights and class map, e.g. `ls models/model.onnx models/class_map.json`, and the calibration file you use on that host.\n\n"
                    "Optional: bring up the Jetson deployment with Docker (run on the device, from a clone of the repo):\n"
                    '`cd "{project_root}" && bash scripts/docker_jetson_build.sh && bash scripts/docker_jetson_up.sh`'
                ),
                "record": "Note JetPack / L4T version and device hostname if this install is for a runbook.",
            },
            {
                "item": "CSI camera smoke passes",
                "verify": "On the device, run `bash scripts/jetson_csi_setup.sh`, or a short `edge.main` run with `--camera csi` (see DEPLOYMENT_JETSON for flags).",
                "record": "If a flip method or sensor id was required, put it in Notes.",
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
                "verify": "In the Documentation section on this page, open the TEST_PLAN item (docs/TEST_PLAN.md) and skim the parts for phases 5–9 you plan to use. Use the other doc links on the same page for detail.",
                "record": "Optionally, note in Notes which phase block you will qualify first.",
            },
        ],
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
            entry: dict[str, Any] = {
                "item": str(item.get("item", "")),
                "verify": str(item.get("verify", "")),
                "record": str(item.get("record", "")),
            }
            va = item.get("verify_actions")
            if isinstance(va, list) and va:
                entry["verify_actions"] = va
            out.append(entry)
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
    mjpeg_port: int = 8001


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
    def setup_context(request: Request) -> dict[str, Any]:
        return {
            "project_root": str(_PROJECT_ROOT),
            "launch_enabled": os.environ.get("SETUP_ALLOW_LAUNCH", "").strip() == "1",
            "markdown_installed": _HAS_MARKDOWN,
            "api_port": _api_port_from_request(request),
            "api_default_port": DEFAULT_API_PORT,
            "mjpeg_default_port": DEFAULT_MJPEG_PORT,
        }

    @router.get("/api/setup/steps")
    def setup_steps() -> dict[str, Any]:
        return {"steps": normalized_steps()}

    @router.get("/api/setup/edge-health")
    def setup_edge_health(
        port: int = Query(
            ...,
            ge=1,
            le=65535,
            description="TCP port where `edge.main` MjpegServer listens (e.g. --mjpeg-port)",
        ),
    ) -> dict[str, Any]:
        """Server-side probe of http://127.0.0.1:{port}/health (browser cannot fetch this cross-origin)."""
        url = f"http://127.0.0.1:{port}/health"
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if resp.status != 200:
                    return {"ok": False, "port": port, "detail": f"HTTP {resp.status}"}
                raw = resp.read(64)
        except urllib.error.HTTPError as e:
            return {"ok": False, "port": port, "detail": f"HTTP {e.code}"}
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            reason = getattr(e, "reason", None)
            if reason is not None and str(reason):
                d = str(reason)
            else:
                d = str(e) or "unreachable"
            return {"ok": False, "port": port, "detail": d}
        try:
            body = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        if not body.startswith("ok"):
            return {
                "ok": False,
                "port": port,
                "detail": (body[:200] or "unexpected /health body"),
            }
        return {"ok": True, "port": port, "detail": None}

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
