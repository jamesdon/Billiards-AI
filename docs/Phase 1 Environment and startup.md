# Phase 1: Environment and startup

## Goal

Bring up edge + backend reliably and verify core services.

## 1) Create and activate environment

```bash
cd "/home/$USER/Billiards AI"
python3 -m venv "/home/$USER/Billiards AI/.venv"
source "/home/$USER/Billiards AI/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -r "/home/$USER/Billiards AI/requirements.txt"
```

## 2) Quick integrity checks

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
python -m compileall "/home/$USER/Billiards AI/core" "/home/$USER/Billiards AI/edge" "/home/$USER/Billiards AI/backend"
ruff check "/home/$USER/Billiards AI"
pytest -q "/home/$USER/Billiards AI/tests"
```

## 3) Start backend

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
curl -s "http://127.0.0.1:8000/health"
curl -s "http://127.0.0.1:8000/live/state"
```

## 4) Start edge (no model smoke test)

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
python -m edge.main --camera 0 --mjpeg-port 8080
```

In another terminal:

```bash
curl -I "http://127.0.0.1:8080/mjpeg"
```

## Pass criteria

- backend `/health` returns `{"ok":true}`
- edge process runs without crash for at least 5 minutes
- MJPEG endpoint responds with `200`

## Docker alternative (Jetson recommended)

```bash
cd "/home/$USER/Billiards AI"
scripts/docker_jetson_build.sh
scripts/docker_jetson_up.sh
curl -s "http://127.0.0.1:8000/health"
curl -I "http://127.0.0.1:8080/mjpeg"
```

