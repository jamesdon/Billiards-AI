# 4. Classification and identity

**Canonical first-time runbook:** the setup wizard at **`GET /setup`** → step **Classification and identity** (`setup_guide.py` `phase4`). It uses **phases 1–5** (no separate “start backend” step while you are already in the wizard), a live panel from `/api/setup/profiles-status`, and optional **Bootstrap minimal profile**. You can ignore this file if the wizard is enough.

## Goal

Validate ball classes and persistent **player/stick profile** records (stable ids and nicknames in `identities.json` via the backend). This is **not** face recognition, logins, or “user detection” in the security sense: profiles are file-backed labels tied to tracking, as produced when edge and the API run together.

---

## Workflow: start → success

Follow these **phases in order**. Each **gate** tells you when you may continue. (Same table is spelled out in the setup wizard without requiring this file.)

| Phase | What you do | Gate (do not continue until) |
| --- | --- | --- |
| **1. One identities path** | Same file for API (`BILLIARDS_IDENTITIES_PATH` or default) and `edge.main` `--identities`. | You can name that path (absolute if unsure). |
| **2. Edge running** | Start `edge.main` with that flag **only if** it is not already up (e.g. **§3**). Check MJPEG **edge /health** in the sidebar. | Edge answers; stream can run. |
| **3. Non-empty profiles** | `GET /profiles`, live panel, camera in view, or **Bootstrap** / minimal JSON. | At least one `players` or `sticks` row. |
| **4. Set a name** | Score Keeper or `PATCH` with a **real** id. | New `display_name` in `GET /profiles`. |
| **5. Persistence (recommended)** | Restart API or edge once; same identities file. | Name still on disk. |

**If you are reading `/setup` in a browser, the API is already running—do not start a second `run_backend.sh` on the same port.** Only use **Environment and startup** / `run_backend.sh` when nothing is listening or the sidebar API lamp is red. “Port already in use” from the script means a server is already there.

### 1. Preconditions

1. You have completed or can run **§3**-class bring-up: `models/model.onnx`, `models/class_map.json`, and a working camera path for `edge.main`.
2. Pick **one** identities file path and use it everywhere:
   - **Recommended:** absolute path, e.g. `/Users/you/Billiards-AI/identities.json` (macOS) or `/home/you/Billiards-AI/identities.json` (Linux/Jetson).
   - The **backend** reads `BILLIARDS_IDENTITIES_PATH` if set; otherwise **`./identities.json` relative to the directory where you start uvicorn**. If that disagrees with edge’s `--identities`, you will see **empty** profiles or **split** files.
3. **Gate:** you can state the single path aloud: “edge writes here, API reads here.”

### 2. Edge (not the API in the common case)

If **Detection and tracking** already left `edge.main` running with `--identities`, keep it. Otherwise start `edge.main` with the same `--identities` path as phase 1 (see **§3** command block in the setup wizard). **Do not** re-run `run_backend.sh` just to read the wizard.

### 3. Until `GET /profiles` is non-empty

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

### 4. Set a display name

**Preferred (UI):** open `http://127.0.0.1:8000/scorekeeper` → **Player & stick names** → type name → **Save** → **Refresh list** → confirm.

**CLI:** copy a real `id` from the **GET** output. Do **not** use the string `PLAYER_ID` from examples.

```bash
curl -s -X PATCH "http://127.0.0.1:8000/profiles/player/REAL_ID_FROM_GET" \
  -H "Content-Type: application/json" \
  -d '{"display_name":"TestName"}'
```

**Gate:** `GET /profiles` shows `display_name: "TestName"` (or your string) for that `id`.

### 5. Persistence check (recommended)

1. Stop **only** the backend **or** **only** `edge.main`. Start it again with the **same** `--identities` / `BILLIARDS_IDENTITIES_PATH` as before.
2. `GET /profiles` again.
3. **Gate:** the `display_name` you set in **D** is still present.

### Sign-off (this step is success)

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
