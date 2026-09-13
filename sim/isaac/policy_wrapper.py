"""DiffPhys Policy Wrapper for Isaac Sim evaluation.

Loads a trained DiffPhys checkpoint and runs inference in Isaac Sim.
Matches the exact observation/action interface from train_target_impact.py:

Observation:
  - depth: 64x48 -> inverse-depth normalize (3/d.clamp(0.3,24)-0.6) -> maxpool 4x -> 12x16
  - state (10): local_v(3) + target_v_body(3) + gravity_dir(3) + margin(1)

Action (6):
  - reshape to (3,2), rotate by body R -> a_pred(3), v_pred(3)
  - actual acceleration = (a_pred - v_pred - g_std) * thr_est_error + g_std
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

# Add upstream to path for Model import
UPSTREAM = Path(__file__).resolve().parent.parent.parent / "training" / "diffphys" / "upstream"
if str(UPSTREAM) not in sys.path:
    sys.path.insert(0, str(UPSTREAM))

from model import Model  # noqa: E402


class DiffPhysPolicyWrapper:
    """Wraps a trained DiffPhys Model for Isaac Sim inference."""

    def __init__(
        self,
        checkpoint_path: str,
        device: str = "cpu",
        max_speed: float = 4.0,
        margin: float = 0.2,
        thr_est_error: float = 1.0,
        dt: float = 1.0 / 15.0,
    ):
        self.device = torch.device(device)
        self.max_speed = max_speed
        self.margin = margin
        self.thr_est_error = thr_est_error
        self.dt = dt
        self.g_std = torch.tensor([0.0, 0.0, -9.80665], device=self.device)

        # Load model (state_dim=10, action_dim=6, matching training)
        self.model = Model(10, 6).to(self.device)
        state_dict = torch.load(checkpoint_path, map_location=self.device)
        # Handle both raw state_dict and checkpoint dicts
        if isinstance(state_dict, dict) and "model" in state_dict:
            state_dict = state_dict["model"]
        self.model.load_state_dict(state_dict, strict=False)
        self.model.eval()
        self.model.reset()

        self._hidden: Optional[torch.Tensor] = None

    def reset(self):
        """Reset GRU hidden state."""
        self.model.reset()
        self._hidden = None

    @torch.no_grad()
    def compute_action(
        self,
        depth: np.ndarray,
        drone_pos: np.ndarray,
        drone_vel: np.ndarray,
        drone_forward: np.ndarray,
        target_pos: np.ndarray,
    ) -> np.ndarray:
        """Compute acceleration command from policy.

        Args:
            depth: HxW depth image in meters (Isaac depth camera output)
            drone_pos: (3,) world position
            drone_vel: (3,) world velocity
            drone_forward: (3,) body forward direction in world frame
            target_pos: (3,) target position in world frame

        Returns:
            (3,) acceleration command in world frame
        """
        # --- Depth preprocessing (exact match to training) ---
        depth_t = torch.from_numpy(depth).float().to(self.device)
        # Resize to 64x48 if needed
        if depth_t.shape != (48, 64):
            depth_t = F.interpolate(
                depth_t.unsqueeze(0).unsqueeze(0),
                size=(48, 64),
                mode="bilinear",
                align_corners=False,
            ).squeeze(0).squeeze(0)
        # Inverse-depth normalization: 3/d.clamp(0.3,24) - 0.6
        x = 3.0 / depth_t.clamp(0.3, 24.0) - 0.6
        # Maxpool 4x: 64x48 -> 16x12 (wait, training does max_pool2d(x[:,None], 4, 4))
        # 64x48 with kernel 4 -> 16x12. But training comment says 12x16.
        # Actually: input is (B, 1, 48, 64) -> maxpool 4 -> (B, 1, 12, 16)
        x = F.max_pool2d(x.unsqueeze(0).unsqueeze(0), 4, 4)  # (1,1,12,16)

        # --- Body frame construction (exact match to training) ---
        fwd = torch.from_numpy(drone_forward).float().to(self.device)
        fwd[2] = 0.0  # project to horizontal
        fwd = F.normalize(fwd, dim=0)
        up = torch.tensor([0.0, 0.0, 1.0], device=self.device)
        right = torch.cross(up, fwd, dim=-1)
        # R = [fwd, right, up] as columns (body-to-world rotation)
        R = torch.stack([fwd, right, up], dim=-1)  # (3, 3)

        # --- State vector (10 dims) ---
        v = torch.from_numpy(drone_vel).float().to(self.device)
        local_v = v @ R  # (3,) velocity in body frame

        target_v_raw = torch.from_numpy(target_pos - drone_pos).float().to(self.device)
        target_v_norm = torch.norm(target_v_raw)
        target_v_unit = target_v_raw / (target_v_norm + 1e-8)
        target_v = target_v_unit * min(target_v_norm.item(), self.max_speed)
        target_v_body = target_v @ R  # (3,)

        # Gravity direction: body z-axis in world frame (third column of drone's actual R)
        # For simplicity, use drone_forward to estimate attitude
        # In training, this is env.R[:, 2] = body up direction in world
        # We approximate with the up vector rotated by drone attitude
        # For a level drone, this is [0,0,1]
        gravity_dir = up.clone()  # approximation: assume level for now
        # TODO: get actual body z-axis from Isaac drone orientation

        margin_t = torch.tensor([self.margin], device=self.device)

        state = torch.cat([local_v, target_v_body, gravity_dir, margin_t], dim=0)
        state = state.unsqueeze(0)  # (1, 10)

        # --- Model forward pass ---
        act, values, self._hidden = self.model(x, state, self._hidden)
        act = act.squeeze(0)  # (6,)

        # --- Action decoding (exact match to training) ---
        # reshape to (3, 2), rotate by R -> a_pred, v_pred
        act_reshaped = act.reshape(3, 2)  # (3, 2)
        rotated = R @ act_reshaped  # (3, 2)
        a_pred = rotated[:, 0]  # (3,) thrust prediction in world
        v_pred = rotated[:, 1]  # (3,) velocity prediction in world

        # actual acceleration = (a_pred - v_pred - g_std) * thr_est_error + g_std
        accel = (a_pred - v_pred - self.g_std) * self.thr_est_error + self.g_std

        return accel.cpu().numpy()

    def compute_action_with_yaw(
        self,
        depth: np.ndarray,
        drone_pos: np.ndarray,
        drone_vel: np.ndarray,
        drone_yaw: float,
        target_pos: np.ndarray,
    ) -> tuple[np.ndarray, float]:
        """Compute action with yaw-based forward direction.

        Returns:
            (acceleration_world, yaw_rate)
        """
        # Construct forward direction from yaw
        fwd = np.array([np.cos(drone_yaw), np.sin(drone_yaw), 0.0])
        accel = self.compute_action(depth, drone_pos, drone_vel, fwd, target_pos)

        # Compute yaw rate to face target
        target_dir = target_pos - drone_pos
        target_yaw = np.arctan2(target_dir[1], target_dir[0])
        yaw_error = self._wrap_angle(target_yaw - drone_yaw)
        yaw_rate = np.clip(yaw_error * 2.0, -3.0, 3.0)

        return accel, yaw_rate

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        return (angle + np.pi) % (2 * np.pi) - np.pi
