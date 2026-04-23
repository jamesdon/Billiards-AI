"""
Guided setup wizard: step metadata + optional persisted progress (local JSON).

Open in browser after starting the backend: GET /setup

**The wizard text in `SETUP_STEPS` is the source of truth for first-time system setup.**
Long-form `docs/*.md` files are optional background; the checklist + How to verify blocks must be
enough to complete the flow without them.

The setup wizard (static/setup/app.js) treats Markdown-style triple backtick fences as
paste-ready command blocks (Copy in **How to verify** only). Single backticks are inline
code only. Put runnable shell in ``` ``` blocks, not only in `inline` backticks.

Docs (optional): GET /api/setup/doc?path=docs%2FTEST_PLAN.md (markdown rendered to HTML)

Optional local script launch: POST /api/setup/launch (requires SETUP_ALLOW_LAUNCH=1 and 127.0.0.1).
"""
from __future__ import annotations

import errno
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

from core.identities_path import identities_json_str

from .lan_url import public_http_base_info

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
    "small": "16px",
    "medium": "22px",
    "large": "28px",
}


def _text_size_doc_viewer_css() -> str:
    """Sync /api/setup/doc <html> font rules with _TEXT_SIZE_TO_PX (avoid drift from /setup)."""
    p = _TEXT_SIZE_TO_PX
    return (
        f'html[data-text-size="small"]{{font-size:{p["small"]} !important;}}\n'
        f'html[data-text-size="medium"]{{font-size:{p["medium"]} !important;}}\n'
        f'html[data-text-size="large"]{{font-size:{p["large"]} !important;}}\n'
        f'html:not([data-text-size]){{font-size:{p["medium"]} !important;}}'
    )


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
        "title": "Environment and startup",
        "summary": "Create the venv, install dependencies, and **start the API once** (`./scripts/run_backend.sh` or your process manager) so `/setup` and `/health` work. **Later steps assume the API is already up**—if the sidebar shows the API as healthy, do not start a second server on the same port. **Pick your platform first** (`uname -s` / `uname -m` → **`docs/1 Environment and startup.md` §0–§1c**): Linux ARM64 (Jetson CSI) differs from macOS / Linux x86.",
        "checklist": [
            {
                "item": "Virtual environment exists at .venv",
                "verify": "From the repository root, run `test -d .venv && echo OK`. You should see `OK`. If not, run step 1) of the next checklist line (core dependencies install) first, then re-check this box.",
                "record": "If you rebuilt the venv, note the date and `.venv` Python version in Notes.",
            },
            {
                "item": "Core dependencies install without error",
                "verify": (
                    "1) **Detect the machine** (run at the repo root). Use the output to choose the matching section in "
                    "**`docs/1 Environment and startup.md`** (§0 table → §1a / §1b / §1c).\n\n"
                    "```bash\n"
                    "/usr/bin/uname -s\n"
                    "/usr/bin/uname -m\n"
                    "```\n\n"
                    "- **Linux + aarch64 or arm64** (Jetson-family): follow **§1a** in that doc (apt `python3-opencv`, "
                    "`python3 -m venv --system-site-packages`, then `pip install -r requirements.txt`). "
                    "A plain `python3 -m venv .venv` **without** §1a is the usual reason `import cv2` fails or CSI sees "
                    "`GStreamer: NO`. Do **not** install `requirements-train.txt` in the **same** venv if you need CSI "
                    "(Ultralytics installs pip OpenCV).\n\n"
                    "- **Linux + x86_64** or **Darwin** (macOS): you can use this one-liner, then the import check below.\n\n"
                    "```bash\n"
                    'cd "{project_root}" && python3 -m venv .venv && .venv/bin/python3 -m pip install -U pip && '
                    ".venv/bin/python3 -m pip install -r requirements.txt\n"
                    "```\n\n"
                    "2) Confirm **onnxruntime** and **cv2** import (on Jetson after §1a, `cv2` usually loads from "
                    "`/usr/lib/.../dist-packages`; expect one line `imports-ok`, no traceback).\n\n"
                    "```bash\n"
                    '.venv/bin/python3 -c "import onnxruntime,cv2; print(\'imports-ok\')"\n'
                    "```\n\n"
                    "3) **Optional — training only:** if you need Ultralytics on **this** machine **and** you are **not** "
                    "using Jetson CSI in the same venv, install:\n\n"
                    "```bash\n"
                    'cd "{project_root}" && .venv/bin/python3 -m pip install -r requirements-train.txt\n'
                    "```\n\n"
                    "On **Linux ARM64 + CSI**, use a **separate** clone/venv for training, or expect to repair OpenCV per "
                    "**`README.md`** (Jetson repair block) and **`docs/1`** §1a."
                ),
                "record": "If pip or the import check failed, paste the last error lines in Notes. If a package upgrade was unexpected, name it in Notes.",
            },
        ],
        "links": [],
        "hints": [
            "Optional (Jetson with CSI only): with the venv active, from the repository root run `bash scripts/phase1.sh`. That script installs Python deps, checks that OpenCV was built with GStreamer (needed for CSI), runs compileall, ruff, pytest, then smoke-tests the backend and edge with `--camera csi`. It is not a generic desktop check—do not expect it to succeed on macOS or on a system without a CSI camera and a GStreamer-capable OpenCV; use the Environment checklist on those machines instead."
        ],
        "doc_refs": [{"label": "1 — Environment and startup", "path": "docs/1 Environment and startup.md"}],
    },
    {
        "id": "model",
        "title": "Detector model (ONNX)",
        "summary": "Place `models/model.onnx` and `models/class_map.json` in the tree. No separate numbered section in TEST_PLAN — this is the artifact required before the **edge vision** step (detection, tracking, classification, profiles). For training or export, see “Dataset and training (optional)”.",
        "checklist": [
            {
                "item": "models/model.onnx exists",
                "verify": (
                    "**If `models/model.onnx` is missing**, you either **train + export** on this clone or **copy** an ONNX "
                    "that matches **`models/class_map.json`** (normal deploy: copy team file; see **`docs/MODEL_OPTIMIZATION.md`**).\n\n"
                    "**Path A — already trained here** (`runs/detect/*/weights/best.pt` exists): from the repository root run:\n\n"
                    "```bash\n"
                    'cd "{project_root}" && bash scripts/jetson_yolo_export_latest.sh\n'
                    "bash scripts/publish_trained_model.sh\n"
                    "# optional: GIT_PUSH=1 bash scripts/publish_trained_model.sh\n"
                    "```\n\n"
                    "**Path B — no training runs yet:** install dataset images under `data/datasets/billiards/images/train/` "
                    "(and val), then `bash scripts/jetson_yolo_train.sh`, then run **`jetson_yolo_export_latest.sh`** again. "
                    "Capture/label hints: **`docs/MODEL_OPTIMIZATION.md`**, **`scripts/jetson_capture_training_frames.sh`**.\n\n"
                    "**Path C — ONNX produced elsewhere:** Prefer merging via **git** (train machine runs **`publish_trained_model.sh`** "
                    "and pushes). If you must hand-copy once, place the file at **`models/model.onnx`** and run "
                    "**`bash scripts/publish_trained_model.sh`** so the binary is tracked like any other artifact.\n\n"
                    "Confirm on disk (typical size a few to tens of MB):\n\n"
                    "```bash\n"
                    "ls -lh models/model.onnx\n"
                    "```"
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
        "title": "Calibration and coordinate mapping",
        "summary": "Homography + six pocket points saved to calibration.json (TEST_PLAN §2). On macOS, start_calibration.sh defaults to USB; on Jetson, CSI. Use the interactive GUI (desktop or X11). Complete the checklists on this page only, then use Save / next step. You do not start the full detector+MJPEG table overlay in this step; the next step (**Detection, tracking, classification, and identity**) does that with your model files and this calibration file.",
        "checklist": [
            {
                "item": "calibration.json produced for this camera + table",
                "verify": (
                    "1) From the repository root, start the interactive calibration flow (GUI; needs a desktop or forwarded display on Jetson):\n\n"
                    "```bash\n"
                    'cd "{project_root}" && bash scripts/start_calibration.sh\n'
                    "```\n\n"
                    "2) Confirm your output file and inspect JSON for a 3×3 homography and six pockets (see CALIBRATION and §2 docs for structure). Example for the default file name:\n\n"
                    "```bash\n"
                    "ls -l calibration.json\n"
                    "```"
                ),
                "record": "If the path is not the default, or you used a table preset, put that in Notes.",
            },
            {
                "item": "Pocket labels match the schema (see calibration doc)",
                "verify": (
                    "On Jetson or Linux, optional automated checks (invalid labels should show in logs):\n\n"
                    "```bash\n"
                    'cd "{project_root}" && bash scripts/phase2.sh\n'
                    "```"
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
        ],
        "hints": [
            "macOS: `start_calibration.sh` defaults to a USB camera and only requires venv + NumPy<2 + `import cv2` (pip opencv, no GStreamer). Jetson: CSI + GStreamer-backed OpenCV for production. Grant Camera to Terminal / iTerm / VS Code."
        ],
        "doc_refs": [
            {"label": "CALIBRATION", "path": "docs/CALIBRATION.md"},
            {"label": "2 — Calibration and coordinate mapping", "path": "docs/2 Calibration and coordinate mapping.md"},
        ],
    },
    {
        "id": "phase3",
        "title": "Detection, tracking, classification, and identity",
        "summary": (
            "Single **edge.main** run covers TEST_PLAN **§3 (detection + tracks)** and **§4 (ball labels + player/stick profiles)**. You need `models/model.onnx`, `models/class_map.json`, and `calibration.json`. "
            "Start **edge** (MJPEG), not a second `run_backend.sh`—if you opened this wizard, the **API is already running**.\n\n"
            "**(A) Detection/tracking** — raw boxes vs stable **trk** IDs on the video. **(B) Ball class labels** — suffix on ball tracks (cue / solid / stripe / …). "
            "**(C) Profiles** — **`{project_root}/identities.json`** (see **Live profile status**); edge writes rows for people/cue sticks; Score Keeper names them. **Work the checklist in order**; do not set **display_name** before a profile **id** exists."
        ),
        "checklist": [
            {
                "item": "`edge.main` is running: MJPEG + /health OK, detector output visible, and track boxes stay sensible when things move",
                "verify": (
                    "**API:** only start `run_backend.sh` if the API lamp is red. **This step is `edge.main` only (MJPEG on the sidebar port).**\n\n"
                    "Paste **once** in a new terminal (Jetson: `--camera csi`, omit `--usb-index`). **`--show-track-debug-overlay`** is for bring-up; drop it for a clean table view later. **`--identities`** is repo **`identities.json`** — the file the API/Score Keeper use — so the **same** process covers detection through profiles without a restart.\n\n"
                    "```bash\n"
                    'cd "{project_root}"\n'
                    'source "{project_root}/.venv/bin/activate"\n'
                    "python3 -m edge.main \\\n"
                    "  --camera usb \\\n"
                    "  --usb-index 0 \\\n"
                    '  --onnx-model "{project_root}/models/model.onnx" \\\n'
                    '  --class-map "{project_root}/models/class_map.json" \\\n'
                    '  --calib "{project_root}/calibration.json" \\\n'
                    '  --identities "{project_root}/identities.json" \\\n'
                    "  --show-track-debug-overlay \\\n"
                    "  --mjpeg-port {mjpeg_port}\n"
                    "```\n\n"
                    "Set the sidebar **MJPEG** field to the same port. Use the buttons. On the video: **top-right panel** (ONNX, frame/inference counts), **thin** `ball 0.87` = raw detector, **thicker** `trk …` = **tracks**. **ONNX: NO** means a bad/missing model path. **Model outputs: 0** = nothing above threshold (move the camera). **Track IDs** should not flicker randomly when motion is smooth. A **port 8000 in use** message from `run_backend.sh` is expected if the API is already up."
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
                "record": "Note camera, USB index, or MJPEG port in Notes if non-default.",
            },
            {
                "item": "Ball **tracks** show plausible type labels (cue / 8 / solid / stripe) on the video",
                "verify": (
                    "Open the **Open MJPEG** view (or the tab you already had from the previous line). **Find a ball track** (thicker box, label starts with `trk ball id …` when `--show-track-debug-overlay` is on). The short **suffix** after the track id is the **classifier** output (e.g. solid/stripe/cue), not the raw YOLO class name. "
                    "In the top-right **Vision debug** panel, raw detector boxes are the thin “ball 0.87” style; **tracks** are the thicker ones.\n\n"
                    "Move balls if needed so at least one ball is tracked. **You are done** when labels are **roughly** right for your table (occasional “unknown” under bad light is not a hard failure; systematic wrong types mean lighting, model, or `class_map` need work—see the **Detector model** and **Calibration** steps).\n\n"
                    "This line is **ball class labels only**; profiles are the next checkboxes."
                ),
                "verify_actions": [
                    {
                        "label": "Open MJPEG overlay",
                        "href_template": "http://127.0.0.1:{mjpeg_port}/mjpeg",
                    },
                ],
                "record": "If something is always UNKNOWN or wrong, note lighting and a sample label in Notes.",
            },
            {
                "item": "At least one **player** or **stick** profile exists in `identities.json` (Live status = green) **or** you bootstrapped for API-only smoke",
                "verify": (
                    "**Prerequisite for naming:** `GET /profiles` must not be two empty lists. The **Live profile status** line turns **green** when `player_count + stick_count` is at least 1 (same data as the buttons below).\n\n"
                    "**Get rows from the camera (normal):** with edge running, put **a person and/or a cue stick** in view (class names depend on your `class_map`, often `person` / `player` and `cue_stick` / `stick`). **Balls alone** do not create a player entry; wait 10–20 s, then refresh or open **Open GET /profiles**.\n\n"
                    "**No camera?** use **Bootstrap minimal profile** to insert one test player, or save this JSON as **`{project_root}/identities.json`** and re-check `GET`:\n\n"
                    "```json\n"
                    "{\n"
                    '  "players": [\n'
                    '    { "id": "manual-smoke-1", "display_name": "Test", "color_signature": [] }\n'
                    "  ],\n"
                    '  "sticks": []\n'
                    "}\n"
                    "```\n\n"
                    "**If counts stay at zero,** edge may not be persisting yet—keep a person or stick in view 10–20 s, or confirm edge is running with `--identities \"{project_root}/identities.json\"` as in the command above."
                ),
                "verify_actions": [
                    {
                        "label": "Open GET /profiles",
                        "href_template": "http://127.0.0.1:{api_port}/profiles",
                    },
                    {
                        "label": "Bootstrap minimal profile (if empty)",
                        "action": "bootstrap_minimal_profiles",
                    },
                ],
                "record": "If you had to bootstrap, say so in Notes (camera unavailable vs other).",
            },
            {
                "item": "A **display_name** is set for a real `id` and shows up in `GET /profiles`",
                "verify": (
                    "Open **Open Score Keeper** → **Player & stick names** → edit → **Save** → **Refresh list**, or use `curl` with an id copied from **Open GET /profiles** (not a placeholder like `PLAYER_ID`):\n\n"
                    "```bash\n"
                    "curl -s http://127.0.0.1:{api_port}/profiles\n"
                    "curl -s -X PATCH \"http://127.0.0.1:{api_port}/profiles/player/REAL_ID_FROM_JSON\" -H \"Content-Type: application/json\" -d '{\"display_name\":\"TestName\"}'\n"
                    "curl -s http://127.0.0.1:{api_port}/profiles\n"
                    "```\n\n"
                    "Use `/profiles/stick/…` for stick ids. **You are done** when the last `GET` shows your new name next to the same `id`."
                ),
                "verify_actions": [
                    {
                        "label": "Open Score Keeper",
                        "href_template": "http://127.0.0.1:{api_port}/scorekeeper",
                    },
                    {
                        "label": "Open GET /profiles",
                        "href_template": "http://127.0.0.1:{api_port}/profiles",
                    },
                ],
                "record": "If PATCH 404s, you likely used a placeholder id or wrong player/stick path—paste the id you used in Notes.",
            },
            {
                "item": "(Recommended) The display name still appears after you restart **only** the API or **only** `edge.main`",
                "verify": (
                    "Stop and start **one** process, not both at once if you can help it. The API and edge must keep using **`{project_root}/identities.json`** (default for both when you use `run_backend.sh` and the same edge command as above). Open **Open GET /profiles (after restart)**. **You are done** when the edited `display_name` is still there.\n\n"
                    "If `/setup` does not load, re-check **Environment and startup** (one `uvicorn` on the API port)."
                ),
                "verify_actions": [
                    {
                        "label": "Open GET /profiles (after restart)",
                        "href_template": "http://127.0.0.1:{api_port}/profiles",
                    },
                ],
                "record": "If the name did not round-trip, put the id and the last `GET` body in Notes.",
            },
        ],
        "links": [
            {"label": "GET /profiles (JSON)", "href_template": "http://127.0.0.1:{api_port}/profiles"},
            {"label": "Score Keeper (edit names)", "href_template": "http://127.0.0.1:{api_port}/scorekeeper"},
            {"label": "Edge /health (MJPEG port in sidebar)", "href_template": "http://127.0.0.1:{mjpeg_port}/health"},
        ],
        "hints": [
            "Jetson: replace `--camera usb` / `--usb-index` with `--camera csi` (same `edge.main` block as the first checklist line).",
            "Sidebar GET /health on the MJPEG port only means edge is listening, not that tracking is good on its own—use the video.",
            "CUDA provider warnings on Mac are normal; CoreML/CPU is used. `--show-track-debug-overlay` is bring-up only.",
            "404 on `PATCH` with a copied example id: you likely left the literal string `PLAYER_ID` or a typo—ids must come from the current `GET /profiles` JSON.",
            "Empty `GET /profiles` with edge running: only balls in frame (need person or stick in view to create rows), or edge is not the same `edge.main` you started with the default `--identities` path.",
        ],
        "doc_refs": [
            {"label": "3 — Detection and tracking", "path": "docs/3 Detection and tracking.md"},
            {"label": "4 — Classification and identity", "path": "docs/4 Classification and identity.md"},
        ],
    },
    {
        "id": "dataset_training",
        "title": "Dataset and training (optional)",
        "summary": "Roboflow Universe → merge → train → export. Use when you need a new detector; typical flow is to complete the **Detection, tracking, classification, and identity** step with an existing `model.onnx` first, then return here to refresh weights and re-run the same edge smoke.",
        "checklist": [
            {
                "item": "ROBOFLOW_API_KEY available in the shell that downloads data",
                "verify": (
                    "1) In the shell you will use for downloads, run `test -n \"$ROBOFLOW_API_KEY\" && echo set` (never paste the key into Notes).\n\n"
                    "2) To pull a Universe sample and merge, on the same machine, from the repository root, set the key in that shell and run:\n\n"
                    "```bash\n"
                    'cd "{project_root}" && export ROBOFLOW_API_KEY=… && bash scripts/universe_dataset_pipeline.sh\n'
                    "```\n\n"
                    "(Replace the ellipsis token in the line above with your key, or rely on the variable already in the environment.)"
                ),
                "record": "A note like “key is in my shell profile” is enough. Do not store the secret in Notes.",
            },
            {
                "item": "billiards-data.yaml paths are valid on this machine",
                "verify": (
                    "1) Open `data/datasets/billiards/billiards-data.yaml` and check that the dataset `path` points at real directories on this machine.\n\n"
                    "2) To train and export a model on this machine (after the environment step), from the repository root:\n\n"
                    "```bash\n"
                    'cd "{project_root}" && bash scripts/jetson_yolo_train.sh && bash scripts/jetson_yolo_export_latest.sh\n'
                    "```"
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
        "title": "Jetson deployment",
        "summary": "On-device runbook: copy artifacts, CSI camera, optional Docker + TensorRT (`docs/DEPLOYMENT_JETSON.md`).",
        "checklist": [
            {
                "item": "models/ and calibration copied to the Jetson tree",
                "verify": (
                    "On the device, confirm weights and class map, e.g. `ls models/model.onnx models/class_map.json`, and the calibration file you use on that host.\n\n"
                    "Optional: bring up the Jetson deployment with Docker (run on the device, from a clone of the repo):\n\n"
                    "```bash\n"
                    'cd "{project_root}" && bash scripts/docker_jetson_build.sh && bash scripts/docker_jetson_up.sh\n'
                    "```"
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
        "title": "Events, rules, stats, backend, and acceptance",
        "summary": "After the camera path works (steps above), these areas close the loop: edge emits **events** → **rules** update game state → **stats** and dashboards read persisted data → an **end-to-end** run proves it on your table. The checklist is the map; use Documentation links only when you need more depth.",
        "checklist": [
            {
                "item": "You know which downstream areas you are qualifying next (at least one of the five below)",
                "verify": (
                    "**5 — Events / fouls:** Edge (or a bridge) should send `shot_start`, `shot_end`, `ball_pocketed`, `ball_collision`, `rail_hit`, and foul-type events; you verify timing and that the backend or logs show them. "
                    "If nothing arrives, check that something is `POST`ing to this API and that the table/camera run matches your wiring.\n\n"
                    "**6 — Rules / end of game:** Pick a game mode in your config and run until win/loss or rack reset; scores and innings should follow the mode’s rules, not just raw detections.\n\n"
                    "**7 — Stats / analytics:** After several shots, your chosen stats (per player, per shot) should update in whatever surface you use (DB, API, or export) without contradictions to the event stream.\n\n"
                    "**8 — Backend persistence:** Confirm events or snapshots you care about are stored (SQLite or configured store) and survive an API restart on the same data directory.\n\n"
                    "**9 — Acceptance / demo:** A full short session (rack → shots → at least one pocketed event → visible scoreboard) with no unexplained gaps; that is the practical gate for “ship it” on this rig.\n\n"
                    "There are no extra quick links in this step—use **Open API /health** below and your usual edge URLs from earlier steps. Optional deep dives: Documentation items (TEST_PLAN gate table, event docs, acceptance runbook)."
                ),
                "record": "Note which number (5–9) you validated first, and one concrete symptom if something failed (e.g. no SHOT_END).",
            },
        ],
        "links": [
            {"label": "API /health (this server)", "href_template": "http://127.0.0.1:{api_port}/health"},
        ],
        "hints": [
            "You will not get useful §5+ behavior until the edge vision step (§3+§4) and your rules wiring match your deployment (same repo paths, same API URL).",
        ],
        "doc_refs": [
            {"label": "TEST_PLAN (gate table)", "path": "docs/TEST_PLAN.md"},
            {"label": "EVENT_DETECTION", "path": "docs/EVENT_DETECTION.md"},
            {"label": "9 — End-to-end acceptance", "path": "docs/9 End-to-end acceptance.md"},
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


def _client_localhost_or_testclient(request: Request) -> bool:
    """True for local browser, or ASGI test clients (e.g. Starlette `testclient`)."""
    if _client_localhost(request):
        return True
    h = (getattr(request.client, "host", None) or "").strip()
    return h in ("testclient",)


def _is_econnrefused(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and exc.errno == errno.ECONNREFUSED:
        return True
    inner = getattr(exc, "reason", None)
    if isinstance(inner, OSError) and inner.errno == errno.ECONNREFUSED:
        return True
    return False


def build_router() -> APIRouter:
    router = APIRouter(tags=["setup"])

    @router.get("/setup", response_class=HTMLResponse, include_in_schema=True)
    def setup_page() -> HTMLResponse:
        html_path = _STATIC / "setup" / "index.html"
        if not html_path.is_file():
            return HTMLResponse("<h1>Setup UI missing</h1><p>Rebuild repo; expected backend/static/setup/index.html</p>", status_code=500)
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @router.get("/scorekeeper", response_class=HTMLResponse, include_in_schema=True)
    def scorekeeper_page() -> HTMLResponse:
        html_path = _STATIC / "scorekeeper" / "index.html"
        if not html_path.is_file():
            return HTMLResponse(
                "<h1>Score Keeper UI missing</h1><p>Expected backend/static/scorekeeper/index.html</p>",
                status_code=500,
            )
        return HTMLResponse(html_path.read_text(encoding="utf-8"))

    @router.get("/api/setup/context")
    def setup_context(request: Request) -> dict[str, Any]:
        port = _api_port_from_request(request)
        http_info = public_http_base_info(request, port)
        return {
            "project_root": str(_PROJECT_ROOT),
            "launch_enabled": os.environ.get("SETUP_ALLOW_LAUNCH", "").strip() == "1",
            "markdown_installed": _HAS_MARKDOWN,
            "api_port": port,
            "api_default_port": DEFAULT_API_PORT,
            "mjpeg_default_port": DEFAULT_MJPEG_PORT,
            "public_http_base": http_info["public_http_base"],
            "public_http_base_source": http_info["public_http_base_source"],
            "scorekeeper_url": http_info["scorekeeper_url"],
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
            description="TCP port where `edge.main` MjpegServer listens (e.g. `--mjpeg-port`)",
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
            rsn = (
                "connection_refused"
                if _is_econnrefused(e) or "Connection refused" in d
                else "unreachable"
            )
            return {"ok": False, "port": port, "detail": d, "reason": rsn}
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
{_text_size_doc_viewer_css()}
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

    @router.get("/api/setup/profiles-status")
    def setup_profiles_status() -> dict[str, Any]:
        """Player/stick counts and resolved identities file path (same as GET /profiles)."""
        from core.identity_store import IdentityStore

        path = identities_json_str()
        st = IdentityStore(path=path)
        st.load()
        return {
            "identities_path": path,
            "identities_path_resolved": str(Path(path).resolve()),
            "player_count": len(st.players),
            "stick_count": len(st.sticks),
            "nonempty": (len(st.players) + len(st.sticks)) > 0,
        }

    @router.post("/api/setup/bootstrap-minimal-profiles")
    def setup_bootstrap_minimal_profiles(request: Request) -> dict[str, Any]:
        """
        If the identities file has no player/stick rows, write one minimal player for API/UI smoke
        (localhost or TestClient only). Use when you cannot get a person/cue in frame for phase C.
        """
        if not _client_localhost_or_testclient(request):
            raise HTTPException(
                status_code=403, detail="Bootstrap is only allowed from this machine (localhost / test client)"
            )
        from core.identity_store import IdentityStore
        from core.types import PlayerProfile

        path = identities_json_str()
        st = IdentityStore(path=path)
        st.load()
        if st.players or st.sticks:
            return {
                "ok": False,
                "detail": "Identities file already has profiles; do not overwrite. Use camera/edge, or clear the file if you know what you are doing.",
                "player_count": len(st.players),
                "stick_count": len(st.sticks),
            }
        st.upsert_player(
            PlayerProfile(
                id="setup-smoke-1",
                display_name="Setup",
                color_signature=[],
            )
        )
        st.save()
        return {
            "ok": True,
            "message": "Wrote one minimal player with id `setup-smoke-1` (display_name Setup). Continue with phase D: rename in Score Keeper or PATCH.",
        }

    return router
