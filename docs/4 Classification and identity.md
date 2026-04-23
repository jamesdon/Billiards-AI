# 4. Classification and identity

## Goal

Validate ball classes and persistent **player/stick profile** records (stable ids and nicknames in `identities.json` via the backend). This is **not** face recognition, logins, or “user detection” in the security sense: profiles are file-backed labels tied to tracking, as produced when edge and the API run together.

## 1) Start backend and edge with the same identities file

**Objective:** (a) **Ball class labels** behave as you expect. (b) **Player and cue-stick rows** in `identities.json` (stable `id` + `display_name`) are what the scoreboard uses—**not** app logins or face ID.

Use **one long-running** `edge.main` if you already started it in **§3 Detection and tracking** with `--identities` pointing at the file the API uses (`BILLIARDS_IDENTITIES_PATH` or default `./identities.json`). You only need to restart edge if you omitted `--identities` then or you want a cold-start sanity check; otherwise keep the same process.

```bash
cd "/home/$USER/Billiards-AI"
./scripts/run_backend.sh
```

(`run_backend.sh` uses `python3 -m uvicorn` so it still works if `.venv/bin/uvicorn` points at an old path after renaming the project folder. Override port with `BACKEND_PORT`, e.g. `BACKEND_PORT=8000 ./scripts/run_backend.sh`.)

In another terminal (or continue the existing edge from §3 with matching `--identities`):

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --onnx-model "/home/$USER/Billiards-AI/models/model.onnx" --class-map "/home/$USER/Billiards-AI/models/class_map.json" --identities "/home/$USER/Billiards-AI/identities.json"
```

## 2) List and edit display names (Score Keeper or curl)

**Primary:** open **Score Keeper** at `http://127.0.0.1:8000/scorekeeper` and use **Player & stick names** (same as `GET`/`PATCH` `/profiles`). This is a good place to set nicknames at the **start of a session** without touching the terminal.

**JSON check:**

```bash
curl -s "http://127.0.0.1:8000/profiles"
```

### When this returns `{"players":[],"sticks":[]}`

That is **normal** until at least one **player** or **stick** profile has been **created and saved** to `identities.json`. Profiles are **not** pre-seeded: edge creates them when the detector sees objects with labels that map to people or sticks. With the default `models/class_map.json`, that means **`person` / `player` tracks** and **`cue_stick` / `stick` tracks** (see `edge/pipeline.py` and `edge/classify/player_stick_id.py`).

1. **Run `edge.main`** with the same `--identities` path you intend to use in production (e.g. `--identities ./identities.json` from the repo root).
2. **Keep a person in frame** (or a stick, for stick rows) so the YOLO model produces detections. Ball-only frames never create a player row.
3. **Same file, same process cwd:** the FastAPI app reads `BILLIARDS_IDENTITIES_PATH` or default `./identities.json` **relative to the process working directory** when you start uvicorn. If edge writes `…/Billiards-AI/identities.json` and the API was started from another directory, you can get an empty file or a different file — use an **absolute path** for both, or set `BILLIARDS_IDENTITIES_PATH` to the same path edge uses.
4. **Optional (API / rename testing without a camera):** you can add a **minimal** file next to the backend so `GET /profiles` is non-empty (IDs are for persistence/rename; empty `color_signature` is loadable for read/rename only):

   ```json
   {
     "players": [
       { "id": "manual-smoke-1", "display_name": "Test", "color_signature": [] }
     ],
     "sticks": []
   }
   ```

   Save it as the path the backend actually loads (e.g. `./identities.json` in the directory where you start uvicorn, or set `BILLIARDS_IDENTITIES_PATH`). Then `PATCH /profiles/player/manual-smoke-1` can be used to verify the HTTP path.

## 3) Rename player/stick nickname (optional curl)

In Score Keeper, each row’s **Save** calls `PATCH /profiles/player/…` or `PATCH /profiles/stick/…`. From the shell, use an **`id` value** from the JSON in step 2 in the path — strings like `PLAYER_PROFILE_ID` in examples are **placeholders**, not real ids. If the backend returns `no player profile with id ...`, you pasted the example token literally.

```bash
curl -s -X PATCH "http://127.0.0.1:8000/profiles/player/REAL_ID_FROM_curl_profiles" -H "Content-Type: application/json" -d '{"display_name":"Alex"}'
curl -s -X PATCH "http://127.0.0.1:8000/profiles/stick/REAL_STICK_ID_FROM_curl_profiles" -H "Content-Type: application/json" -d '{"display_name":"Break Cue"}'
```

## 4) Verify persistence (restart optional)

Confirm `display_name` values survive after **restarting the backend** and/or **restarting `edge.main`** with the same `--identities` path. You do not have to stop edge only for this test if the file path never changed.

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 --onnx-model "/home/$USER/Billiards-AI/models/model.onnx" --class-map "/home/$USER/Billiards-AI/models/class_map.json" --identities "/home/$USER/Billiards-AI/identities.json"
```

## Pass criteria

- same people/sticks map to stable profile IDs across restarts
- nicknames persist

