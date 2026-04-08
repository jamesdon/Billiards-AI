# Phase 2: Calibration and coordinate mapping

## Goal

Validate calibration schema, pocket labels, and coordinate mapping assumptions.

## 1) Validate pocket labels in calibration JSON

Create/edit calibration file:

```bash
cd "/home/$USER/Billiards-AI"
cat > "/home/$USER/Billiards-AI/calibration.json" <<'EOF'
{
  "H": [[1,0,0],[0,1,0],[0,0,1]],
  "pockets": [
    {"label":"top_left_corner","center_xy_m":[0.0,0.0],"radius_m":0.07},
    {"label":"top_right_corner","center_xy_m":[2.84,0.0],"radius_m":0.07},
    {"label":"bottom_left_corner","center_xy_m":[0.0,1.42],"radius_m":0.07},
    {"label":"bottom_right_corner","center_xy_m":[2.84,1.42],"radius_m":0.07},
    {"label":"left_side_pocket","center_xy_m":[0.0,0.71],"radius_m":0.07},
    {"label":"right_side_pocket","center_xy_m":[2.84,0.71],"radius_m":0.07}
  ]
}
EOF
```

## 2) Load calibration in edge startup

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera 0 --calib "/home/$USER/Billiards-AI/calibration.json" --mjpeg-port 8080
```

## 3) Negative test: invalid pocket label should fail

```bash
cd "/home/$USER/Billiards-AI"
cp "/home/$USER/Billiards-AI/calibration.json" "/home/$USER/Billiards-AI/calibration_invalid.json"
python - <<'PY'
import json
p="/home/$USER/Billiards-AI/calibration_invalid.json"
d=json.load(open(p))
d["pockets"][0]["label"]="top_middle_side"
json.dump(d, open(p,"w"), indent=2)
print("written", p)
PY
```

Run and confirm error:

```bash
cd "/home/$USER/Billiards-AI"
source "/home/$USER/Billiards-AI/.venv/bin/activate"
python -m edge.main --camera 0 --calib "/home/$USER/Billiards-AI/calibration_invalid.json" --mjpeg-port 8081
```

## Pass criteria

- valid `calibration.json` loads successfully
- invalid label is rejected

