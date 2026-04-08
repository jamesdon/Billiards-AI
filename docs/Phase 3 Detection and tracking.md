# Phase 3: Detection and tracking

## Goal

Verify ONNX detection and multi-track stability.

## 1) Prepare class map

```bash
cd "/home/$USER/Billiards AI"
cat > "/home/$USER/Billiards AI/class_map.json" <<'EOF'
{
  "0": "ball",
  "1": "person",
  "2": "cue_stick"
}
EOF
```

## 2) Run edge with ONNX model

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
python -m edge.main \
  --camera 0 \
  --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" \
  --class-map "/home/$USER/Billiards AI/class_map.json" \
  --detect-every-n 2 \
  --mjpeg-port 8080
```

## 3) Run performance sweep

```bash
cd "/home/$USER/Billiards AI"
source "/home/$USER/Billiards AI/.venv/bin/activate"
python -m edge.main --camera 0 --onnx-model "/ABSOLUTE/PATH/TO/model.onnx" --class-map "/home/$USER/Billiards AI/class_map.json" --detect-every-n 1 --mjpeg-port 8082
```

Repeat with `--detect-every-n 3`.

## Pass criteria

- no detector/tracker crashes
- IDs remain stable for moving balls/players/sticks in normal play

