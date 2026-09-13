"""RK3588 inference wrapper.

Loads RKNN model (or ONNX fallback on ARM CPU), runs preprocessing ->
inference -> postprocessing. GRU falls back to CPU if NPU support is poor.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np


class RK3588Inference:
    """Policy inference on RK3588.

    Priority: NPU (RKNN) -> CPU (ONNX Runtime).
    Preprocessing: depth resize + inverse-depth normalization.
    Postprocessing: action denormalization to drone action scale.
    """

    def __init__(self, model_path: str, use_npu: bool = True):
        self.model_path = model_path
        self.use_npu = use_npu
        self._rknn = None
        self._onnx = None
        self._hidden = np.zeros((1, 1, 128), dtype=np.float32)
        self._load()

    def _load(self):
        if self.use_npu and self.model_path.endswith(".rknn"):
            try:
                from rknnlite.api import RKNNLite
                self._rknn = RKNNLite()
                self._rknn.load_rknn(self.model_path)
                self._rknn.init_runtime(core_mask=0)  # NPU core 0
                print("[RK3588] Loaded RKNN model on NPU")
                return
            except ImportError:
                print("[RK3588] rknnlite not available, falling back to ONNX CPU")

        # ONNX Runtime fallback
        try:
            import onnxruntime as ort
            self._onnx = ort.InferenceSession(
                self.model_path, providers=["CPUExecutionProvider"]
            )
            print("[RK3588] Loaded ONNX model on CPU")
        except ImportError:
            print("[RK3588] onnxruntime not available")

    def preprocess(self, depth: np.ndarray) -> np.ndarray:
        """Resize to 320x240, apply inverse-depth normalization."""
        if depth.shape != (240, 320):
            # Simple nearest-neighbor resize
            from PIL import Image
            img = Image.fromarray(depth)
            img = img.resize((320, 240), Image.NEAREST)
            depth = np.array(img, dtype=np.float32)
        # Inverse depth
        with np.errstate(divide="ignore"):
            inv = 1.0 / depth
        inv[~np.isfinite(inv)] = 0.0
        return inv[np.newaxis, np.newaxis, :, :].astype(np.float32)  # (1,1,H,W)

    def postprocess(self, action: np.ndarray) -> np.ndarray:
        """Denormalize action to drone action scale [ax, ay, az, yaw_rate]."""
        scale = np.array([8.0, 8.0, 8.0, 3.14159], dtype=np.float32)
        return action * scale

    def infer(self, depth: np.ndarray, state: np.ndarray) -> np.ndarray:
        """Full inference: preprocess -> model -> postprocess."""
        depth_in = self.preprocess(depth)
        state_in = state[np.newaxis, :].astype(np.float32)

        if self._rknn is not None:
            outputs = self._rknn.inference(inputs=[depth_in, state_in, self._hidden])
            action = outputs[0]
            self._hidden = outputs[1] if len(outputs) > 1 else self._hidden
        elif self._onnx is not None:
            outputs = self._onnx.run(
                None,
                {"depth": depth_in, "state": state_in, "gru_hidden": self._hidden},
            )
            action = outputs[0]
            self._hidden = outputs[1]
        else:
            action = np.zeros((1, 4), dtype=np.float32)

        return self.postprocess(action[0])

    def reset(self):
        self._hidden = np.zeros((1, 1, 128), dtype=np.float32)
