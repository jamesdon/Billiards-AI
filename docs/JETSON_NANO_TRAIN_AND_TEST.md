# On-device train + test (legacy filename)

The canonical guide is **`docs/ORIN_NANO_TRAIN_AND_TEST.md`** (Jetson **Orin Nano**, JetPack **5.x** baseline, Ampere GPU, updated dependency notes). It includes **“How to test (what to run, in order)”** and all `jetson_*.sh` one-liners.

**Live CSI frame capture (for YOLO training data)** — this *is* in the plan; scripts live in `scripts/`:

`cd ~/Billiards-AI && bash scripts/jetson_capture_training_frames.sh --count 300 --stride 20 --prefix my_session`

Defaults write JPEGs to `data/datasets/billiards/images/capture/`. See **`docs/TEST_PLAN.md`** → **“Dataset: live CSI captures for YOLO training”** for the official checklist step.

This file name is retained so older bookmarks and links keep resolving.
