from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np

from core.types import BallObservation

from .detector_base import DetectorConfig
from .postprocess import yolo_like_to_observations


@dataclass
class OnnxRuntimeDetector:
    model_path: str
    cfg: DetectorConfig = DetectorConfig()
    input_name: Optional[str] = None
    output_name: Optional[str] = None
    class_map: Optional[dict[int, str]] = None

    def __post_init__(self) -> None:
        import onnxruntime as ort

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.sess = ort.InferenceSession(self.model_path, providers=providers)
        if self.input_name is None:
            self.input_name = self.sess.get_inputs()[0].name
        if self.output_name is None:
            self.output_name = self.sess.get_outputs()[0].name

    def detect(self, frame_bgr: np.ndarray, ts: float) -> List[BallObservation]:
        inp, meta = self._preprocess(frame_bgr)
        outputs = self.sess.run([self.output_name], {self.input_name: inp})[0]
        preds = self._postprocess(outputs, meta)
        obs = yolo_like_to_observations(
            preds,
            conf_thres=self.cfg.conf_thres,
            iou_thres=self.cfg.iou_thres,
            max_det=self.cfg.max_det,
        )
        if self.class_map:
            out: List[BallObservation] = []
            for o in obs:
                try:
                    cls_id = int(o.label)
                except ValueError:
                    out.append(o)
                    continue
                out.append(BallObservation(bbox_xyxy=o.bbox_xyxy, conf=o.conf, label=self.class_map.get(cls_id, o.label)))
            return out
        return obs

    def _preprocess(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, dict]:
        h0, w0 = frame_bgr.shape[:2]
        w, h = self.cfg.input_w, self.cfg.input_h
        scale = min(w / w0, h / h0)
        nw, nh = int(w0 * scale), int(h0 * scale)
        resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((h, w, 3), 114, dtype=np.uint8)
        pad_x = (w - nw) // 2
        pad_y = (h - nh) // 2
        canvas[pad_y : pad_y + nh, pad_x : pad_x + nw] = resized
        img = canvas[:, :, ::-1].astype(np.float32) / 255.0  # BGR->RGB
        img = np.transpose(img, (2, 0, 1))[None, :, :, :]  # 1x3xHxW
        return img, {"scale": scale, "pad_x": pad_x, "pad_y": pad_y, "w0": w0, "h0": h0}

    def _postprocess(self, raw: np.ndarray, meta: dict) -> np.ndarray:
        """
        Normalize a few common YOLO ONNX output shapes to Nx6.

        Supported:
        - Nx6 already [x1,y1,x2,y2,conf,cls] in letterboxed space (rare)
        - 1xNx6
        - 1xNx(5+C) where conf = obj * max_cls_prob and cls = argmax
        """
        arr = np.array(raw)
        if arr.ndim == 3 and arr.shape[0] == 1:
            arr = arr[0]

        if arr.ndim != 2:
            return np.zeros((0, 6), dtype=np.float32)

        if arr.shape[1] == 6:
            preds = arr.astype(np.float32)
        else:
            # assume [cx,cy,w,h,obj,cls...]
            if arr.shape[1] < 6:
                return np.zeros((0, 6), dtype=np.float32)
            cxcywh = arr[:, 0:4].astype(np.float32)
            obj = arr[:, 4:5].astype(np.float32)
            cls_probs = arr[:, 5:].astype(np.float32)
            cls_idx = np.argmax(cls_probs, axis=1).astype(np.float32)
            cls_conf = np.max(cls_probs, axis=1, keepdims=True).astype(np.float32)
            conf = (obj * cls_conf).reshape(-1, 1)
            cx, cy, bw, bh = np.split(cxcywh, 4, axis=1)
            x1 = cx - bw / 2
            y1 = cy - bh / 2
            x2 = cx + bw / 2
            y2 = cy + bh / 2
            preds = np.concatenate([x1, y1, x2, y2, conf, cls_idx.reshape(-1, 1)], axis=1)

        # map from letterbox input space back to original pixels
        scale = float(meta["scale"])
        pad_x = float(meta["pad_x"])
        pad_y = float(meta["pad_y"])
        preds[:, [0, 2]] -= pad_x
        preds[:, [1, 3]] -= pad_y
        preds[:, 0:4] /= max(scale, 1e-9)
        # clip
        w0 = float(meta["w0"])
        h0 = float(meta["h0"])
        preds[:, 0] = np.clip(preds[:, 0], 0, w0 - 1)
        preds[:, 2] = np.clip(preds[:, 2], 0, w0 - 1)
        preds[:, 1] = np.clip(preds[:, 1], 0, h0 - 1)
        preds[:, 3] = np.clip(preds[:, 3], 0, h0 - 1)
        return preds

