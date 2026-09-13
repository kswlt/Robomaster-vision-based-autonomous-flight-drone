"""Isaac Sim Policy Wrapper for DiffPhys-trained target-impact policy.

Loads a PyTorch checkpoint from DiffPhys training and wraps it for use
in Isaac Sim evaluation. Handles:
- Depth preprocessing (resize, normalize, maxpool) matching training
- State vector construction (local_v, target_v, gravity, margin)
- Action decoding (thrust vector + velocity prediction -> high-level control)
- Coordinate frame consistency (world/body/camera)

This is the bridge between training (DiffPhys CUDA env) and validation (Isaac Sim).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import torch
import torch.nn.functional as F


class IsaacPolicyWrapper:
    """Wraps a DiffPhys-trained Model for Isaac Sim inference.

    Usage:
        policy = IsaacPolicyWrapper("checkpoint.pth", device="cuda")
        action = policy.step(depth_image, drone_state, target_pos)
        # action = (thrust_vector_world, velocity_prediction_world)
    """

    def __init__(
        self,
        checkpoint_path: str,
        device: str = "cuda",
        state_dim: int = 10,
        action_dim: int = 6,
        depth_width: int = 64,
        depth_height: int = 48,
        maxpool_kernel: int = 4,
        ctl_dt: float = 1.0 / 15.0,
        hit_radius: float = 0.3,
    ):
        self.device = torch.device(device)
        self.depth_width = depth_width
        self.depth_height = depth_height
        self.maxpool_kernel = maxpool_kernel
        self.ctl_dt = ctl_dt
        self.hit_radius = hit_radius

        # Import model from upstream
        import sys
        upstream = Path(__file__).resolve().parent.parent / "diffphys" / "upstream"
        if str(upstream) not in sys.path:
            sys.path.insert(0, str(upstream))
        from model import Model

        self.model = Model(state_dim, action_dim).to(self.device)
        state_dict = torch.load(checkpoint_path, map_location=self.device)
        self.model.load_state_dict(state_dict, strict=False)
        self.model.eval()

        self.hidden: Optional[torch.Tensor] = None
        self.g_std = torch.tensor([0.0, 0.0, -9.80665], device=self.device)

    def reset(self):
        """Reset GRU hidden state for new episode."""
        self.hidden = None
        if hasattr(self.model, "reset"):
            self.model.reset()

    def preprocess_depth(self, depth: np.ndarray) -> torch.Tensor:
        """Preprocess depth image to match training pipeline.

        Args:
            depth: (H, W) float32 depth in meters, 0 = invalid/far

        Returns:
            (1, 1, H/4, W/4) normalized depth tensor
        """
        # Resize to training resolution if needed
        if depth.shape != (self.depth_height, self.depth_width):
            # Simple resize via torch
            d = torch.from_numpy(depth).float().unsqueeze(0).unsqueeze(0)
            d = F.interpolate(d, size=(self.depth_height, self.depth_width), mode="bilinear")
            depth = d.squeeze().numpy()

        x = torch.from_numpy(depth).float().to(self.device)
        # Normalize: 3/depth - 0.6 (matching upstream main_cuda.py)
        x = 3.0 / x.clamp(0.3, 24.0) - 0.6
        # Maxpool 4x (matching training)
        x = F.max_pool2d(x.unsqueeze(0).unsqueeze(0), self.maxpool_kernel, self.maxpool_kernel)
        return x

    def build_state(
        self,
        position_world: np.ndarray,
        velocity_world: np.ndarray,
        rotation_matrix: np.ndarray,
        target_position_world: np.ndarray,
        max_speed: float = 8.0,
        margin: float = 0.15,
    ) -> torch.Tensor:
        """Build policy state vector matching DiffPhys observation.

        State = [local_v(3), target_v(3), gravity(3), margin(1)] = 10 dims

        Args:
            position_world: (3,) drone position in world frame
            velocity_world: (3,) drone velocity in world frame
            rotation_matrix: (3,3) body-to-world rotation (columns: forward, left, up)
            target_position_world: (3,) armor target position in world frame
            max_speed: maximum speed for target vector normalization
            margin: drone radius margin for collision

        Returns:
            (1, 10) state tensor
        """
        R = torch.from_numpy(rotation_matrix).float().to(self.device)
        v_world = torch.from_numpy(velocity_world).float().to(self.device)
        p_world = torch.from_numpy(position_world).float().to(self.device)
        p_target = torch.from_numpy(target_position_world).float().to(self.device)

        # Yaw-only rotation for state (matching upstream: zero pitch/roll)
        fwd = R[:, 0].clone()
        fwd[2] = 0.0
        fwd = F.normalize(fwd, dim=0)
        up = torch.tensor([0.0, 0.0, 1.0], device=self.device)
        left = torch.cross(up, fwd)
        R_yaw = torch.stack([fwd, left, up], dim=1)  # (3,3)

        # Local velocity
        local_v = R_yaw.T @ v_world  # (3,)

        # Target vector (clamped to max_speed)
        target_v_raw = p_target - p_world
        target_v_norm = torch.norm(target_v_raw)
        target_v = target_v_raw / (target_v_norm + 1e-8) * torch.minimum(target_v_norm, torch.tensor(max_speed))
        target_v_local = R_yaw.T @ target_v

        # Gravity in body frame
        gravity_local = R_yaw.T @ self.g_std

        state = torch.cat([local_v, target_v_local, gravity_local, torch.tensor([margin], device=self.device)])
        return state.unsqueeze(0)

    @torch.no_grad()
    def step(
        self,
        depth: np.ndarray,
        position_world: np.ndarray,
        velocity_world: np.ndarray,
        rotation_matrix: np.ndarray,
        target_position_world: np.ndarray,
        max_speed: float = 8.0,
        margin: float = 0.15,
        thr_est_error: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run one policy inference step.

        Args:
            depth: (H, W) depth image in meters
            position_world: (3,) drone world position
            velocity_world: (3,) drone world velocity
            rotation_matrix: (3,3) body-to-world rotation
            target_position_world: (3,) armor target world position
            max_speed: max speed for target vector
            margin: collision margin
            thr_est_error: thrust estimation error factor

        Returns:
            thrust_vector_world: (3,) desired acceleration/thrust in world frame
            velocity_prediction_world: (3,) predicted velocity in world frame
        """
        # Preprocess
        x = self.preprocess_depth(depth)
        state = self.build_state(position_world, velocity_world, rotation_matrix, target_position_world, max_speed, margin)

        # Forward
        act, values, self.hidden = self.model(x, state, self.hidden)

        # Decode action: (thrust_body, vel_pred_body) -> world frame
        R = torch.from_numpy(rotation_matrix).float().to(self.device)
        B = 1
        a_pred, v_pred, *_ = (R @ act.reshape(B, 3, -1)).unbind(-1)

        # Thrust correction (matching upstream)
        thrust_world = (a_pred - v_pred - self.g_std) * thr_est_error + self.g_std

        return thrust_world.squeeze(0).cpu().numpy(), v_pred.squeeze(0).cpu().numpy()

    def check_hit(self, position_world: np.ndarray, target_position_world: np.ndarray) -> bool:
        """Check if drone has hit the target."""
        dist = np.linalg.norm(position_world - target_position_world)
        return dist < self.hit_radius
