from __future__ import annotations

import argparse
import json
import time

from core.rules.eight_ball import EightBallRules
from core.rules.nine_ball import NineBallRules
from core.rules.snooker import SnookerRules
from core.rules.straight_pool import StraightPoolRules
from core.rules.uk_pool import UKPoolRules
from core.types import Event, GameConfig, GameState, GameType, PlayerState

from core.identity_store import IdentityStore
from .calib.calib_store import Calibration
from .calib.table_geometry import auto_calibration_from_corners, table_geometry_dict
from .io.camera_opencv import OpenCVCamera, jetson_csi_gstreamer_pipeline, opencv_gstreamer_enabled
from .overlay.draw import draw_overlay
from .overlay.stream_mjpeg import MjpegServer
from .pipeline import EdgePipeline


def _rules_for(game_type: GameType):
    if game_type == GameType.EIGHT_BALL:
        return EightBallRules()
    if game_type == GameType.NINE_BALL:
        return NineBallRules()
    if game_type == GameType.STRAIGHT_POOL:
        return StraightPoolRules()
    if game_type == GameType.UK_POOL:
        return UKPoolRules()
    if game_type == GameType.SNOOKER:
        return SnookerRules()
    raise ValueError(f"Unsupported game_type={game_type}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--camera",
        default="csi",
        help="Camera source: csi (Jetson default), usb, numeric index, file path, or explicit gstreamer string",
    )
    ap.add_argument("--usb-index", type=int, default=0, help="USB camera index used when --camera usb")
    ap.add_argument("--csi-sensor-id", type=int, default=0)
    ap.add_argument("--csi-framerate", type=int, default=30)
    ap.add_argument("--csi-flip-method", type=int, default=0)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--calib", type=str, default=None, help="Calibration JSON with homography + pockets")
    ap.add_argument(
        "--auto-calib-out",
        type=str,
        default=None,
        help="Write a generated calibration JSON from 4 corners and exit",
    )
    ap.add_argument(
        "--table-size",
        type=str,
        default="9ft",
        choices=["7ft", "8ft", "9ft", "snooker"],
        help="Table size preset used by --auto-calib-out",
    )
    ap.add_argument(
        "--table-corners-px",
        type=str,
        default=None,
        help="Required with --auto-calib-out. Four corners TL,TR,BL,BR as 'x1,y1;x2,y2;x3,y3;x4,y4'",
    )
    ap.add_argument(
        "--pocket-radius-m",
        type=float,
        default=0.07,
        help="Pocket radius (meters) used by --auto-calib-out",
    )
    ap.add_argument("--game", type=str, default="8ball", choices=[g.value for g in GameType])
    ap.add_argument("--mjpeg-port", type=int, default=8080)
    ap.add_argument("--players", type=str, default="Player A,Player B")
    ap.add_argument("--onnx-model", type=str, default=None, help="YOLO-like ONNX model path (optional)")
    ap.add_argument("--class-map", type=str, default=None, help="JSON file mapping class_id->label")
    ap.add_argument("--identities", type=str, default="./identities.json", help="Persisted player/stick profiles")
    ap.add_argument("--detect-every-n", type=int, default=2)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.auto_calib_out:
        if not args.table_corners_px:
            raise ValueError("--auto-calib-out requires --table-corners-px")
        chunks = [c.strip() for c in str(args.table_corners_px).split(";") if c.strip()]
        if len(chunks) != 4:
            raise ValueError("--table-corners-px requires exactly 4 points TL,TR,BL,BR")
        corners: list[tuple[float, float]] = []
        for c in chunks:
            parts = [p.strip() for p in c.split(",")]
            if len(parts) != 2:
                raise ValueError(f"Invalid corner format: {c!r}")
            corners.append((float(parts[0]), float(parts[1])))
        size_presets = {
            "7ft": (1.981, 0.991),
            "8ft": (2.235, 1.118),
            "9ft": (2.84, 1.42),
            "snooker": (3.569, 1.778),
        }
        table_length_m, table_width_m = size_presets[str(args.table_size)]
        calib, geom = auto_calibration_from_corners(
            image_points=corners,
            table_length_m=table_length_m,
            table_width_m=table_width_m,
            pocket_radius_m=float(args.pocket_radius_m),
        )
        calib.save(str(args.auto_calib_out))
        print(f"Wrote calibration: {args.auto_calib_out}")
        print(json.dumps(table_geometry_dict(geom), indent=2))
        return
    cam_src: int | str
    use_gstreamer = False
    cam_arg = str(args.camera).strip().lower()
    if cam_arg == "csi":
        w = int(args.width or 1280)
        h = int(args.height or 720)
        if not opencv_gstreamer_enabled():
            raise RuntimeError(
                "CSI camera mode requires OpenCV with GStreamer support, but current cv2 build has "
                "GStreamer=NO. On Jetson, remove pip OpenCV wheels and use system OpenCV.\n"
                "Suggested fix:\n"
                "  /usr/bin/python3 -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless\n"
                "  sudo /usr/bin/apt-get install -y python3-opencv python3-gst-1.0 gstreamer1.0-tools\n"
                "  # recreate virtualenv with system site packages\n"
                "  /usr/bin/python3 -m venv --system-site-packages /home/$USER/Billiards-AI/.venv"
            )
        cam_src = jetson_csi_gstreamer_pipeline(
            sensor_id=int(args.csi_sensor_id),
            capture_width=w,
            capture_height=h,
            display_width=w,
            display_height=h,
            framerate=int(args.csi_framerate),
            flip_method=int(args.csi_flip_method),
        )
        use_gstreamer = True
    elif cam_arg == "usb":
        cam_src = int(args.usb_index)
    elif str(args.camera).isdigit():
        cam_src = int(args.camera)
    else:
        # allow explicit gstreamer source if it contains typical marker
        cam_src = str(args.camera)
        if "!" in cam_src or "nvarguscamerasrc" in cam_src:
            use_gstreamer = True

    players = [PlayerState(name=p.strip()) for p in args.players.split(",") if p.strip()]
    if len(players) < 2:
        players = [PlayerState("Player A"), PlayerState("Player B")]

    cfg = GameConfig(game_type=GameType(args.game), num_players=len(players))
    state = GameState(config=cfg, players=players)
    state.resolve_rotation()

    rules = _rules_for(cfg.game_type)
    calib = Calibration.load(args.calib) if args.calib else None

    pipeline = EdgePipeline()
    pipeline.cfg.detect_every_n = int(args.detect_every_n)
    if args.onnx_model:
        from .vision.detector_onnxruntime import OnnxRuntimeDetector

        class_map = None
        if args.class_map:
            with open(str(args.class_map), "r", encoding="utf-8") as f:
                raw = json.load(f)
            class_map = {int(k): str(v) for k, v in raw.items()}
        pipeline.detector = OnnxRuntimeDetector(model_path=str(args.onnx_model), class_map=class_map)

    store = IdentityStore(path=str(args.identities))
    store.load()
    pipeline.identity_store = store
    from .classify.player_stick_id import PlayerStickIdentifier

    pipeline.player_stick_id = PlayerStickIdentifier(store=store)

    mjpeg = MjpegServer(port=int(args.mjpeg_port))
    mjpeg.start()

    cam = OpenCVCamera(source=cam_src, width=args.width, height=args.height, use_gstreamer=use_gstreamer)
    last = time.time()
    for ts, frame in cam.frames():
        def on_event(ev: Event) -> None:
            rules.on_event(state, ev)

        pipeline.step(state=state, frame_bgr=frame, ts=ts, calib=calib, on_event=on_event)
        out = draw_overlay(frame, state, player_name=state.current_player().name)
        mjpeg.update(out)

        # lightweight FPS print cadence
        now = time.time()
        if now - last > 2.0:
            last = now


if __name__ == "__main__":
    main()

