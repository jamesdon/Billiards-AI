# TCP ports (Billiards-AI)

All **default** HTTP services in this repo use these six ports on `127.0.0.1` (**8000** = API only; **8001–8005** = MJPEG and phase scripts). Override with `BACKEND_PORT` / `--mjpeg-port` / script env only when you must.

| Port | Role |
|------|------|
| **8000** | FastAPI / setup guide (`uvicorn`, `scripts/run_backend.sh`, `BACKEND_PORT`) |
| **8001** | Default MJPEG for `edge.main` (live overlay, `scripts/phase3.sh` baseline segment, Docker edge) |
| **8002** | `scripts/phase2.sh` — valid-calibration MJPEG smoke |
| **8003** | `scripts/phase2.sh` — invalid-label MJPEG smoke |
| **8004** | `scripts/phase3.sh` — `detect_every_n=1` sweep |
| **8005** | `scripts/phase3.sh` — `detect_every_n=3` sweep |

Do not bind **MJPEG** on **8000** (that is the API). The setup sidebar “MJPEG port” field defaults to **8001** and should stay in **8001–8005** for normal work.
