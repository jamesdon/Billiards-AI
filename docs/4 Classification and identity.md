# 4. Classification and identity

## Goal

Validate ball classes and persistent **player/stick profile** records (stable ids and nicknames in `identities.json` via the backend). This is **not** face recognition, logins, or “user detection” in the security sense: profiles are file-backed labels tied to tracking, as produced when edge and the API run together.

## 1) Start backend and edge with identities file

```bash
cd "/home/$USER/Billiards-AI"
./scripts/run_backend.sh
```

(`run_backend.sh` uses `python3 -m uvicorn` so it still works if `.venv/bin/uvicorn` points at an old path after renaming the project folder. Override port with `BACKEND_PORT`, e.g. `BACKEND_PORT=8000 ./scripts/run_backend.sh`.)

In another terminal:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --onnx-model "/home/$USER/Billiards-AI/models/model.onnx" --class-map "/home/$USER/Billiards-AI/models/class_map.json" --identities "/home/$USER/Billiards-AI/identities.json"
```

## 2) List profiles

```bash
curl -s "http://127.0.0.1:8000/profiles"
```

## 3) Rename player/stick nickname

```bash
curl -s -X PATCH "http://127.0.0.1:8000/profiles/player/PLAYER_PROFILE_ID" -H "Content-Type: application/json" -d '{"display_name":"Alex"}'
curl -s -X PATCH "http://127.0.0.1:8000/profiles/stick/STICK_PROFILE_ID" -H "Content-Type: application/json" -d '{"display_name":"Break Cue"}'
```

## 4) Restart edge and verify persistence

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --onnx-model "/home/$USER/Billiards-AI/models/model.onnx" --class-map "/home/$USER/Billiards-AI/models/class_map.json" --identities "/home/$USER/Billiards-AI/identities.json"
```

## Pass criteria

- same people/sticks map to stable profile IDs across restarts
- nicknames persist

