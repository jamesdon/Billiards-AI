from __future__ import annotations

import argparse
import time
import json

from core.rules.eight_ball import EightBallRules
from core.rules.nine_ball import NineBallRules
from core.rules.snooker import SnookerRules
from core.rules.straight_pool import StraightPoolRules
from core.rules.uk_pool import UKPoolRules
from core.types import Event, GameConfig, GameState, GameType, PlayerState

from core.identity_store import IdentityStore
from .calib.calib_store import Calibration
from .io.camera_opencv import OpenCVCamera, jetson_csi_gstreamer_pipeline
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
    cam_src: int | str
    use_gstreamer = False
    cam_arg = str(args.camera).strip().lower()
    if cam_arg == "csi":
        w = int(args.width or 1280)
        h = int(args.height or 720)
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

