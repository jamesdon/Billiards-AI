# Hardware: Arducam IMX477 + lens, audio for referee fouls

## Camera

- **Arducam IMX477 HQ** module for Jetson + **1/4" M12 2.1 mm low-distortion** lens.
- **Why it matters**: lower optical distortion reduces reliance on aggressive **digital** dewarp; homography and projector alignment stay more linear at the cushion line.
- **Jetson setup**: use NVIDIA / Arducam driver guides for **CSI** lane mode and `nvarguscamerasrc` pipeline; re-run `scripts/jetson_csi_setup.sh` after hardware swaps.

## Calibration note

- Re-capture **calibration.json** when changing lens or projector geometry.
- If the field of view changes, update **detector input size** / crop if you train at fixed `imgsz`.

## Audio (micro-fouls)

- **Goal**: correlate **high-sample-rate audio** with `SHOT_START` and cue-ball contact windows to score **double hit**, **push**, and other **micro-fouls** that pixels alone miss.
- **Capture**: ALSA device on Jetson (e.g. `hw:1,0`) or USB mic; `edge/audio/capture.py` + optional `edge/audio/mic_stream.py` (`sounddevice`, `requirements-audio.txt`) feed the same ring buffer used by `--mic-device` on `edge.main`.
- **PortAudio on Jetson / Ubuntu**: `pip install sounddevice` is not enough. Install **`libportaudio2`** (or `portaudio19-dev`, which pulls it in) before importing `sounddevice`, or you get `OSError: PortAudio library not found`. Quick check: `python3 -c "import sounddevice as sd; print(sd.query_devices())"`.
- **Processing**: short-time energy + transient detection → features fed to a lightweight classifier or rule thresholds; timestamp alignment with `GameState.shot` timeline.

## Privacy

- Audio should be **opt-in** per venue; document retention and mute for casual play.
