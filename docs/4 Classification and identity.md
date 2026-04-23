# 4. Classification and identity

**Canonical runbook:** the setup guide at **`GET /setup`**, sidebar step **Classification and identity**. All checklist text, buttons, and the live **profile status** panel are defined in `backend/setup_guide.py` (`id: phase4`). This file is an optional **mirror** of that flow—if anything disagrees, the wizard wins.

## What you are proving

| Track | Meaning |
| --- | --- |
| **(A) Ball type labels** | The **fast classifier** (HSV heuristics on ball ROIs) updates each **ball track** with types such as cue / eight / solid / stripe. You confirm labels on the **MJPEG** overlay look sane with `--show-track-debug-overlay` (track lines start with `trk ball id …`). |
| **(B) Player and stick profiles** | File-backed rows in `identities.json` (`id`, `display_name`, …). Edge **creates** them when it persists **person/player** and **cue_stick/stick** tracks; the API exposes **`GET /profiles`** and Score Keeper edits names. **Not** login, face ID, or “user detection” in a security sense. |

Ball classification **(A)** and profile rows **(B)** are independent: you can have correct ball labels with zero profiles (balls only in frame), or profiles for bring-up with less focus on per-ball typing.

## Checklist order (six lines in the wizard)

1. **Same `identities` file** — API and `edge.main --identities` must point at one on-disk file (`BILLIARDS_IDENTITIES_PATH` vs repo-root `./identities.json` if unset). The live status line at the top of the step shows the resolved path.
2. **`edge.main` + MJPEG + /health** — Edge must be up (often already from **Detection and tracking**). Buttons open the stream and health URL.
3. **Ball track labels** — On MJPEG, inspect ball **tracks** (thick boxes); suffix after the track id is the classifier. Raw thin boxes are detector-only.
4. **Non-empty profiles** — Live status **green** or **Bootstrap** / hand-written JSON for API-only smoke. **Do not** try to `PATCH` names until at least one `id` exists in `GET /profiles`.
5. **`display_name` set** — Score Keeper or `PATCH /profiles/player/{id}` or `/profiles/stick/{id}` with a **real** id from JSON (never the literal `PLAYER_ID` from examples).
6. **(Recommended) Persistence** — Restart **only** the API or **only** edge once; `GET /profiles` should still show the name.

## Quick links (defaults)

- `GET /profiles` — same JSON as the live panel.
- Score Keeper — **Player & stick names**.
- `POST /api/setup/bootstrap-minimal-profiles` — one test row when the file is empty and you cannot use the camera (exposed as a button in the wizard).

## If something goes wrong

| Symptom | Likely cause |
| --- | --- |
| Always empty `GET /profiles` with edge running | Mismatched identities path, or only balls in frame (no person/stick tracks to create rows). |
| 404 on `PATCH` | Wrong id, typo, or `player` vs `stick` path. |
| Name vanishes after restart | Second start used a different `identities` file or cwd. |

## Deeper context (optional)

With the default `models/class_map.json`, YOLO emits generic **ball** detections; **cue / eight / colors** for balls often come from the **ball classifier** on tracks. **`person` / `player`** and **`cue_stick` / `stick`** detections feed **profile** creation in `edge/pipeline.py` and `edge/classify/player_stick_id.py`.

## TEST_PLAN gate (§4)

- Ball labels acceptable for your conditions; **and**
- At least one profile row, `display_name` set, name survives optional restart per the last checklist line.
