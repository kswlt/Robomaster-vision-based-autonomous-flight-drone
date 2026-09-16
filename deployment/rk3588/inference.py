"""RK3588 inference wrapper for DiffPhys CNN+GRU policy.

Model specs (must match training):
  - Depth input: 64x48, normalized as 3/depth.clamp(0.3,24) - 0.6, then max_pool 4x -> 12x16
  - State vector: 10-dim [local_v(3), target_body(3), gravity(3), margin(1)]
  - GRU hidden: 192-dim
  - Output: 6-dim action (reshape to 3x2 -> accel + velocity prediction)

RK3588 deployment:
  - CNN/MLP on NPU (RKNN)
  - GRU on NPU if supported, else ARM CPU
  - Inference target: >30 FPS, <33ms latency

Usage on RK3588:
    from deployment.rk3588.inference import RK3588Policy
    policy = RK3588Policy("policy.rknn", use_npu=True)
    action = policy.infer(depth_64x48, pos, vel, yaw, target_pos)
    # action = {accel: [ax,ay,az], yaw_rate: float}
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np


class RK3588Policy:
    """End-to-end policy inference on RK3588.

    Priority: RKNN NPU -> ONNX Runtime CPU fallback.
    Handles depth preprocessing, state vector construction, GRU state, action decoding.
    """

    DEPTH_H, DEPTH_W = 48, 64
    STATE_DIM = 10
    HIDDEN_DIM = 192
    ACTION_DIM = 6

    def __init__(self, model_path: str, use_npu: bool = True, device: str = "auto"):
        self.model_path = model_path
        self.use_npu = use_npu
        self._rknn = None
        self._onnx = None
        self._hidden = np.zeros((1, self.HIDDEN_DIM), dtype=np.float32)
        self._yaw = 0.0
        self._load(device)

    def _load(self, device: str):
        """Load model: RKNN on NPU, or ONNX on CPU."""
        if self.use_npu and self.model_path.endswith(".rknn"):
            try:
                from rknnlite.api import RKNNLite
                self._rknn = RKNNLite()
                self._rknn.load_rknn(self.model_path)
                # core_mask: 0=NPU0, 1=NPU1, 2=NPU2, 3=NPU0+1, 4=all
                core = {"auto": 0, "npu0": 0, "npu1": 1, "npu2": 2, "all": 4}.get(device, 0)
                self._rknn.init_runtime(core_mask=core)
                print(f"[RK3588] RKNN model loaded on NPU (core_mask={core})")
                return
            except ImportError:
                print("[RK3588] rknnlite not installed, falling back to ONNX CPU")
            except Exception as e:
                print(f"[RK3588] RKNN init failed: {e}, falling back to ONNX CPU")

        # ONNX Runtime CPU fallback
        try:
            import onnxruntime as ort
            sess_opts = ort.SessionOptions()
            sess_opts.intra_op_num_threads = 4  # RK3588 has 4 A76 + 4 A55
            self._onnx = ort.InferenceSession(
                self.model_path, sess_options=sess_opts,
                providers=["CPUExecutionProvider"],
            )
            print("[RK3588] ONNX model loaded on ARM CPU (4 threads)")
        except ImportError:
            print("[RK3588] ERROR: neither rknnlite nor onnxruntime available")

    def normalize_depth(self, depth: np.ndarray) -> np.ndarray:
        """Normalize depth exactly as training: 3/depth.clamp(0.3,24) - 0.6, max_pool 4x.

        Args:
            depth: (H, W) float32, raw depth in meters. Will be resized to 64x48.
        Returns:
            (1, 1, 12, 16) float32, normalized and pooled depth.
        """
        if depth.shape != (self.DEPTH_H, self.DEPTH_W):
            # Resize to 64x48 (nearest neighbor for depth)
            from PIL import Image
            img = Image.fromarray(depth.astype(np.float32))
            img = img.resize((self.DEPTH_W, self.DEPTH_H), Image.NEAREST)
            depth = np.array(img, dtype=np.float32)

        # Inverse depth normalization (exact match to training)
        depth_clamped = np.clip(depth, 0.3, 24.0)
        x = 3.0 / depth_clamped - 0.6

        # Max pool 4x -> 12x16
        x = x.reshape(1, 1, self.DEPTH_H, self.DEPTH_W)
        # Manual max pooling (no torch dependency on RK3588)
        out_h, out_w = self.DEPTH_H // 4, self.DEPTH_W // 4
        pooled = np.zeros((1, 1, out_h, out_w), dtype=np.float32)
        for i in range(out_h):
            for j in range(out_w):
                pooled[0, 0, i, j] = x[0, 0, i*4:(i+1)*4, j*4:(j+1)*4].max()
        return pooled

    def build_state(self, pos: np.ndarray, vel: np.ndarray, yaw: float,
                    target_pos: np.ndarray) -> np.ndarray:
        """Build 10-dim state vector in body frame.

        State = [local_vel(3), target_body(3), gravity_dir(3), margin(1)]
        """
        # Body frame rotation (yaw only)
        cos_y, sin_y = np.cos(yaw), np.sin(yaw)
        fwd = np.array([cos_y, sin_y, 0.0])
        right = np.array([-sin_y, cos_y, 0.0])
        up = np.array([0.0, 0.0, 1.0])
        R = np.column_stack([fwd, right, up])  # world->body columns

        # Local velocity
        local_v = R.T @ vel

        # Target vector in body frame (clamped magnitude)
        tgt_raw = target_pos - pos
        tgt_dist = np.linalg.norm(tgt_raw)
        tgt_unit = tgt_raw / (tgt_dist + 1e-8)
        max_speed = 4.0  # must match training env.max_speed
        tgt_clamped = tgt_unit * min(tgt_dist, max_speed)
        target_body = R.T @ tgt_clamped

        # Gravity direction in body frame (world gravity = [0,0,-1])
        gravity_world = np.array([0.0, 0.0, -1.0])
        gravity_body = R.T @ gravity_world

        # Margin (distance to nearest obstacle / drone_radius - 1)
        # On real drone, this comes from depth min value
        margin = np.array([0.2], dtype=np.float32)  # placeholder, update from depth

        state = np.concatenate([local_v, target_body, gravity_body, margin]).astype(np.float32)
        return state

    def decode_action(self, raw_action: np.ndarray, yaw: float) -> dict:
        """Decode 6-dim model output to world-frame accel + yaw_rate.

        raw_action: (6,) reshape to (3,2): [accel_body(3), vel_pred(3)]
        Returns: {"accel": [ax,ay,az] world frame, "yaw_rate": float}
        """
        act = raw_action.reshape(3, 2)
        a_body = act[:, 0]  # thrust/accel in body frame
        v_pred = act[:, 1]  # velocity prediction

        # Body -> world rotation
        cos_y, sin_y = np.cos(yaw), np.sin(yaw)
        fwd = np.array([cos_y, sin_y, 0.0])
        right = np.array([-sin_y, cos_y, 0.0])
        up = np.array([0.0, 0.0, 1.0])
        R = np.column_stack([fwd, right, up])

        # Transform accel to world frame, add gravity compensation
        g_std = np.array([0.0, 0.0, -9.80665])
        accel_world = R @ a_body - g_std  # thrust - gravity = net accel

        # Yaw rate derived from velocity prediction direction
        # (simplified: use heading error between v_pred and current velocity)
        yaw_rate = 0.0  # In full implementation, compute from v_pred vs current heading

        return {
            "accel": accel_world.astype(np.float32),
            "yaw_rate": float(yaw_rate),
            "v_pred": v_pred.astype(np.float32),
        }

    def infer(self, depth: np.ndarray, pos: np.ndarray, vel: np.ndarray,
              yaw: float, target_pos: np.ndarray) -> dict:
        """Full inference pipeline.

        Args:
            depth: (H,W) raw depth in meters
            pos: (3,) drone position in world frame
            vel: (3,) drone velocity in world frame
            yaw: drone yaw angle (radians)
            target_pos: (3,) target position in world frame
        Returns:
            {"accel": [ax,ay,az], "yaw_rate": float}
        """
        t0 = time.perf_counter()

        # Preprocess
        depth_in = self.normalize_depth(depth)
        state_in = self.build_state(pos, vel, yaw, target_pos)
        state_in = state_in.reshape(1, self.STATE_DIM)
        hidden_in = self._hidden.copy()

        # Inference
        if self._rknn is not None:
            outputs = self._rknn.inference(inputs=[depth_in, state_in, hidden_in])
            raw_action = outputs[0].reshape(-1)
            if len(outputs) > 1:
                self._hidden = outputs[1].reshape(1, self.HIDDEN_DIM)
        elif self._onnx is not None:
            input_names = [i.name for i in self._onnx.get_inputs()]
            feed = {}
            if len(input_names) >= 1:
                feed[input_names[0]] = depth_in
            if len(input_names) >= 2:
                feed[input_names[1]] = state_in
            if len(input_names) >= 3:
                feed[input_names[2]] = hidden_in
            outputs = self._onnx.run(None, feed)
            raw_action = outputs[0].reshape(-1)
            if len(outputs) > 1:
                self._hidden = outputs[1].reshape(1, self.HIDDEN_DIM)
        else:
            raw_action = np.zeros(self.ACTION_DIM, dtype=np.float32)

        # Postprocess
        result = self.decode_action(raw_action, yaw)
        result["latency_ms"] = (time.perf_counter() - t0) * 1000
        return result

    def reset(self):
        """Reset GRU hidden state (call at episode start)."""
        self._hidden = np.zeros((1, self.HIDDEN_DIM), dtype=np.float32)

    def benchmark(self, n_iter: int = 100) -> dict:
        """Run inference benchmark."""
        depth = np.random.rand(self.DEPTH_H, self.DEPTH_W).astype(np.float32) * 10
        pos = np.zeros(3, dtype=np.float32)
        vel = np.zeros(3, dtype=np.float32)
        target = np.array([5.0, 0.0, 1.0], dtype=np.float32)

        latencies = []
        for _ in range(n_iter):
            result = self.infer(depth, pos, vel, 0.0, target)
            latencies.append(result["latency_ms"])

        return {
            "mean_ms": float(np.mean(latencies)),
            "std_ms": float(np.std(latencies)),
            "p95_ms": float(np.percentile(latencies, 95)),
            "fps": float(1000.0 / np.mean(latencies)),
            "n_iter": n_iter,
        }
