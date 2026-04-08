# Phase 4: Classification and identity

## Goal

Validate ball classes and persistent player/stick profiles with nicknames.

## 1) Start backend and edge with identities file

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" --class-map "/home/$USER/Billiards-AI/class_map.json" --identities "/home/$USER/Billiards-AI/identities.json"
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
python -m edge.main --camera csi --csi-sensor-id 0 --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" --class-map "/home/$USER/Billiards-AI/class_map.json" --identities "/home/$USER/Billiards-AI/identities.json"
```

## Pass criteria

- same people/sticks map to stable profile IDs across restarts
- nicknames persist

