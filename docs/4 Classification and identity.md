# 4. Classification and identity

## Goal

Validate ball classes and persistent **player/stick profile** records (stable ids and nicknames in `identities.json` via the backend). This is **not** face recognition, logins, or “user detection” in the security sense: profiles are file-backed labels tied to tracking, as produced when edge and the API run together.

---

## Workflow: start → success

Follow these **phases in order**. Each **gate** tells you when you may continue. The full runbook below is reference; this table is the procedure.

| Phase | What you do | Gate (do not continue until) |
| --- | --- | --- |
| **A. Preconditions** | Model + `class_map.json` available; you know one **absolute** path for `identities.json` that both edge and the API will use. | Path chosen; backend can be started from the repo (or `BILLIARDS_IDENTITIES_PATH` set to that file). |
| **B. Processes** | Start **backend**, then **edge.main** with `--identities ABS_PATH` (same path as **A**). If you already run edge from **§3** with that flag, keep the same process. | `GET http://127.0.0.1:PORT/health` returns OK; edge is running. |
| **C. Non-empty profiles** | Call **`GET /profiles`** (browser or curl). If `players` and `sticks` are both empty: keep edge running, put **people** and/or a **cue stick** in frame until the pipeline creates rows *or* install the **minimal JSON** (optional, no camera). | At least **one** object in `players` or `sticks` in `GET /profiles`. |
| **D. Set a name** | **Score Keeper** (`/scorekeeper`) → **Player & stick names** → edit → **Save**, **Refresh** *or* `PATCH` with a **real** `id` from **C** (never the literal word `PLAYER_ID`). | `GET /profiles` shows your new `display_name`. |
| **E. Persistence (recommended)** | Restart **only the backend** or **only edge** (same `--identities` as **B**). | `GET /profiles` still shows the same `display_name`. |
| **F. Done** | Check the **sign-off** list below. | All boxes checked. |

### A. Preconditions

1. You have completed or can run **§3**-class bring-up: `models/model.onnx`, `models/class_map.json`, and a working camera path for `edge.main`.
2. Pick **one** identities file path and use it everywhere:
   - **Recommended:** absolute path, e.g. `/Users/you/Billiards-AI/identities.json` (macOS) or `/home/you/Billiards-AI/identities.json` (Linux/Jetson).
   - The **backend** reads `BILLIARDS_IDENTITIES_PATH` if set; otherwise **`./identities.json` relative to the directory where you start uvicorn**. If that disagrees with edge’s `--identities`, you will see **empty** profiles or **split** files.
3. **Gate:** you can state the single path aloud: “edge writes here, API reads here.”

### B. Start backend and edge

1. **Terminal 1 — backend** (from repo root so default `identities.json` matches, or export `BILLIARDS_IDENTITIES_PATH`):

   ```bash
   cd "/path/to/Billiards-AI"
   ./scripts/run_backend.sh
   ```

   Override port if needed: `BACKEND_PORT=8000 ./scripts/run_backend.sh`.

2. **Terminal 2 — edge** (use your **§3** command, but **must** include `--identities` pointing to the **same** file as **A**). Example:

   ```bash
   cd "/path/to/Billiards-AI"
   source ".venv/bin/activate"
   python3 -m edge.main --camera csi --csi-sensor-id 0 --csi-flip-method 6 \
     --onnx-model "/path/to/Billiards-AI/models/model.onnx" \
     --class-map "/path/to/Billiards-AI/models/class_map.json" \
     --identities "/path/to/Billiards-AI/identities.json"
   ```

   On macOS dev you may use `--camera usb` and `--usb-index 0` instead of CSI.

3. **Gate:** `curl -s http://127.0.0.1:8000/health` (adjust port) succeeds; edge is running without immediate crash.

### C. Until `GET /profiles` is non-empty

1. Run:

   ```bash
   curl -s "http://127.0.0.1:8000/profiles"
   ```

   Or open the setup guide **GET /profiles** quick link.

2. **If** both arrays are empty:
   - **Normal** if no person/stick tracks have been persisted yet. Keep **edge** running. Ensure the frame includes **people** and/or a **cue stick** (YOLO classes that map to player/stick — not balls alone). Wait and **GET** again.
   - **Path mismatch:** confirm edge’s `--identities` and the API’s file are the same on disk (`ls -l` both paths if unsure).
   - **No camera / API-only smoke test:** write a **minimal** `identities.json` (see [Minimal file (no camera)](#minimal-file-no-camera)) at the path the backend loads, then **GET** again.

3. **Gate:** JSON contains at least one `"id"` under `players` or `sticks`.

### D. Set a display name

**Preferred (UI):** open `http://127.0.0.1:8000/scorekeeper` → **Player & stick names** → type name → **Save** → **Refresh list** → confirm.

**CLI:** copy a real `id` from the **GET** output. Do **not** use the string `PLAYER_ID` from examples.

```bash
curl -s -X PATCH "http://127.0.0.1:8000/profiles/player/REAL_ID_FROM_GET" \
  -H "Content-Type: application/json" \
  -d '{"display_name":"TestName"}'
```

**Gate:** `GET /profiles` shows `display_name: "TestName"` (or your string) for that `id`.

### E. Persistence check (recommended)

1. Stop **only** the backend **or** **only** `edge.main`. Start it again with the **same** `--identities` / `BILLIARDS_IDENTITIES_PATH` as before.
2. `GET /profiles` again.
3. **Gate:** the `display_name` you set in **D** is still present.

### F. Sign-off (this step is success)

- [ ] `GET /profiles` lists at least one profile (`players` or `sticks`).
- [ ] A `display_name` was set (Score Keeper or `PATCH`) and **GET** reflects it.
- [ ] (Recommended) After **E**, names still match — confirms persistence to disk.

---

## If something goes wrong

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `GET /profiles` always `[]` / `[]` | No tracks yet, or file path split | Put people/cue in frame; align `--identities` and API path; see [C](#c-until-getprofiles-is-non-empty). |
| `no player profile with id 'PLAYER_ID'` | Example curl used **literally** | Use a real `id` from `GET /profiles` in the URL. |
| 404 for a copied id | Typo or wrong kind (player vs stick) | Use `/profiles/player/…` for ids under `players`, `/profiles/stick/…` for `sticks`. |
| Name reverts after restart | Different identities file on second start | Fix path; use absolute paths in scripts. |

---

## Reference: one long-running `edge.main`

If **§3** already started `edge.main` with `--identities` set to the file the API uses, **do not** restart edge only for this step. Add profiles by having people/sticks in frame, then use Score Keeper or `GET`/`PATCH`.

---

## Reference: `curl` examples (placeholders)

These commands use **words like `PLAYER_ID` as documentation**, not real ids:

```bash
curl -s "http://127.0.0.1:8000/profiles"
curl -s -X PATCH "http://127.0.0.1:8000/profiles/player/REAL_ID_FROM_curl_profiles" -H "Content-Type: application/json" -d '{"display_name":"Alex"}'
curl -s -X PATCH "http://127.0.0.1:8000/profiles/stick/REAL_STICK_ID_FROM_curl_profiles" -H "Content-Type: application/json" -d '{"display_name":"Break Cue"}'
```

---

## Minimal file (no camera)

If you need a non-empty `GET /profiles` without a live person/stick (rename API only), save this as the **exact** file path the backend loads (e.g. repo-root `identities.json` when uvicorn cwd is the repo), then `GET` / `PATCH` / `GET`:

```json
{
  "players": [
    { "id": "manual-smoke-1", "display_name": "Test", "color_signature": [] }
  ],
  "sticks": []
}
```

`PATCH` example: `PATCH /profiles/player/manual-smoke-1` with `{"display_name":"Alex"}`.

---

## Deeper context (optional read)

### Why can `{"players":[],"sticks":[]}` be normal?

Profiles are **not** pre-seeded. Edge creates them when the detector sees class labels that map to people or sticks. With the default `models/class_map.json`, that means **`person` / `player` tracks** and **`cue_stick` / `stick` tracks** (see `edge/pipeline.py` and `edge/classify/player_stick_id.py`). Ball-only frames do not create a player row.

### Pass criteria (TEST_PLAN alignment)

- Ball class behavior matches expectations in play.
- Player/stick profile **ids** are stable enough for your table setup; **display names** persist in `identities.json` through API restarts (and edge restarts when using the same file).
