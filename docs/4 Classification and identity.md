# 4. Classification and identity

**Canonical runbook:** **`GET /setup`** → **Detection, tracking, classification, and identity** (covers **§3** and **§4**; `backend/setup_guide.py` `id: phase3`). If this file disagrees with the wizard, the wizard wins.

**One file for everyone:** player/stick data is always **`<repo>/identities.json`**. The API, Score Keeper, and `edge.main` (default `--identities`) all use that path from code.

## (A) Ball type labels

The ROI classifier updates **ball tracks** (cue, eight, solid, stripe, …). On MJPEG with `--show-track-debug-overlay`, ball track labels look like `trk ball id N …` with a short type suffix. Raw thin “ball 0.87” boxes are detector-only.

## (B) Player and stick profiles

`identities.json` stores **id** and **display_name** for the scoreboard. Edge creates rows from **person/player** and **cue_stick/stick** tracks. **Balls alone** do not create a player. **Not** login or face ID.

## Wizard checklist (five lines, in order)

1. **edge + MJPEG + /health** — one `edge.main` command; `--identities` is `{project_root}/identities.json` (see **`docs/3 Detection and tracking.md`** for the same command context).
2. **Ball track labels** — quick sanity on the stream.
3. **Nonempty profiles** — **Live profile status** green, or **Bootstrap** (no camera), or hand-edit **`{project_root}/identities.json`**. Do not rename before you have a real `id`.
4. **display_name** — Score Keeper or `PATCH` with that id.
5. **(Optional) Restart** one of API or edge; name should remain.

## When something fails

| Symptom | What to check |
| --- | --- |
| `GET /profiles` always `[]` with edge | Only balls in frame, or edge not using the repo’s default identity path. |
| 404 on `PATCH` | Typo, or `player` vs `stick` URL, or you used an example `PLAYER_ID` string literally. |
| Name gone after restart | Unusual now that the path is fixed; confirm you did not hand-edit a different file. |

## TEST_PLAN §4

Ball labels usable in practice; at least one profile; `display_name` set; optional restart check.

