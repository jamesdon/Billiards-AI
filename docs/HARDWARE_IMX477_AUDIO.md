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

### Deployed rig (Orin Nano, reference)

- **Microphones**: **Movo VXR10-Pro** (compact shotgun).
- **Analog path**: each mic’s **3.5 mm TRS** plug → **Movo USB-AC** TRS-to-USB adapter (USB audio interface).
- **Cabling**: **USB extension** from each adapter into the Nano’s **first** USB host ports (closest / primary pair—re-check `arecord -l` / `dmesg` after any replug; card index order can change).
- **Kernel / ALSA name**: adapters enumerate as **GeneralPlus USB Audio Device** (two units → typically **`hw:0,0`** and **`hw:1,0`** when those ports win card 0 and 1). Use `arecord -l` and `/proc/asound/cards` to confirm after cable or hub changes.

### Testing without speakers

You do not need **`aplay`** or headphones on the Nano. Record a few seconds, then inspect level in the shell or copy the WAV elsewhere.

```bash
chmod +x /home/jdonn/Billiards-AI/scripts/test_venue_usb_mics_headless.sh
RECORD_SECONDS=4 bash /home/jdonn/Billiards-AI/scripts/test_venue_usb_mics_headless.sh
```

Optional: treat very quiet captures as failure after you tap the table (`peak_abs` should jump):

```bash
MIN_PEAK=800 RECORD_SECONDS=4 bash /home/jdonn/Billiards-AI/scripts/test_venue_usb_mics_headless.sh
```

Match **`edge/audio/mic_stream.py`** sample rate (48 kHz) if you want parity with `--mic-device`:

```bash
SAMPLE_RATE=48000 MIC_DEVICES="plughw:0,0 plughw:1,0" RECORD_SECONDS=3 \
  bash /home/jdonn/Billiards-AI/scripts/test_venue_usb_mics_headless.sh
```

Single-file stats only: `/home/jdonn/Billiards-AI/scripts/jetson_mic_peak_check.py /tmp/your.wav`

### Asymmetric peaks after swapping USB ports

`hw:0,0` vs `hw:1,0` is **enumeration order**, not “left vs right USB socket.” After replugging, **`arecord -l`** and **`/proc/asound/cards`** still name **card 0** as whichever device won **card 0** this boot — often the same physical dongle if it always sits on the same bus path.

If one path stays near **peak_abs ~250** and the other in the **thousands**, **unplug one dongle entirely** and test each chain alone (only one card exists → it becomes **`hw:0,0`**):

```bash
# Chain A only (unplug the other USB-AC from the Nano)
RECORD_SECONDS=4 MIC_DEVICES="hw:0,0" bash /home/jdonn/Billiards-AI/scripts/test_venue_usb_mics_headless.sh
# Power cycle or replug, then chain B only
RECORD_SECONDS=4 MIC_DEVICES="hw:0,0" bash /home/jdonn/Billiards-AI/scripts/test_venue_usb_mics_headless.sh
```

Whichever run stays **~250** while you clap at **that** mic isolates the fault to **that** VXR10, TRS plug, extension, or USB-AC. Optional: **`/usr/bin/lsusb -t`** after each layout to match **USB topology** to **`/proc/asound/cards`**.

## Privacy

- Audio should be **opt-in** per venue; document retention and mute for casual play.
