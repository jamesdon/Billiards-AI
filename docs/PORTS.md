# TCP ports (Billiards-AI)

All **default** HTTP services in this repo use these six ports on `127.0.0.1` (**8000** = API only; **8001–8005** = MJPEG and phase scripts). Override with `BACKEND_PORT` / `--mjpeg-port` / script env only when you must.

**LAN / other devices:** bind the API with **`BACKEND_HOST=0.0.0.0`** (or `uvicorn --host 0.0.0.0`) so phones and tablets on the same network can open the **Score Keeper** app at **`http://<this-machine-LAN-IP>:8000/scorekeeper`**. The setup guide (`GET /setup`) reads **`GET /api/setup/context`** for `public_http_base` and `scorekeeper_url` (QR in the sidebar) when the Host header or a LAN guess is available.

| Port | Role |
|------|------|
| **8000** | FastAPI + browser **setup guide** at **`/setup`**, **Score Keeper** at **`/scorekeeper`** (also embeddable from the setup tab switcher) — start with **`scripts/run_backend.sh`** (uses `python3 -m uvicorn`; `BACKEND_PORT` / `BACKEND_HOST`). See **`README.md`**. |
| **8001** | Default MJPEG for `edge.main` (live overlay, Docker edge) |
| **8002** | `scripts/phase2.sh` — valid-calibration MJPEG smoke |
| **8003** | `scripts/phase2.sh` — invalid-label MJPEG smoke |
| **8004** | alternate MJPEG port for a second `edge.main` (if you need it) |
| **8005** | alternate MJPEG port for a second `edge.main` (if you need it) |

Do not bind **MJPEG** on **8000** (that is the API). The setup sidebar “MJPEG port” field defaults to **8001** and should stay in **8001–8005** for normal work.
