"""Domain randomization for Isaac Sim evaluation.

Disabled in phase 1. Added progressively per curriculum stage 4-6.
Each randomization type has its own ablation flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class RandomizationConfig:
    mass_variation: bool = False
    mass_std: float = 0.1  # fraction of nominal
    init_velocity_random: bool = False
    init_velocity_std: float = 1.0
    control_delay_ms: float = 0.0
    depth_delay_ms: float = 0.0
    depth_noise: bool = False
    depth_noise_std: float = 0.01
    depth_holes: bool = False
    depth_hole_prob: float = 0.0
    frame_drop: bool = False
    frame_drop_prob: float = 0.0
    camera_extrinsic_perturbation: bool = False
    camera_position_std: tuple = (0.0, 0.0, 0.0)
    camera_rotation_std_deg: tuple = (0.0, 0.0, 0.0)
    fov_perturbation_deg: float = 0.0


class DomainRandomizer:
    """Applies domain randomization per episode/step.

    Phase 1: all disabled. Each type can be enabled independently for ablation.
    """

    def __init__(self, cfg: RandomizationConfig | None = None):
        self.cfg = cfg or RandomizationConfig()
        self._rng = np.random.default_rng()

    def randomize_mass(self, nominal_mass: float) -> float:
        if self.cfg.mass_variation:
            return nominal_mass * (1.0 + self._rng.normal(0, self.cfg.mass_std))
        return nominal_mass

    def randomize_init_velocity(self) -> np.ndarray:
        if self.cfg.init_velocity_random:
            return self._rng.normal(0, self.cfg.init_velocity_std, size=3)
        return np.zeros(3)

    def randomize_depth(self, depth: np.ndarray) -> np.ndarray:
        """Apply depth noise, holes, clipping."""
        out = depth.copy()
        if self.cfg.depth_noise:
            out += self._rng.normal(0, self.cfg.depth_noise_std, size=out.shape)
        if self.cfg.depth_holes:
            mask = self._rng.random(out.shape) < self.cfg.depth_hole_prob
            out[mask] = 0.0
        return out

    def should_drop_frame(self) -> bool:
        if self.cfg.frame_drop:
            return self._rng.random() < self.cfg.frame_drop_prob
        return False

    def randomize_camera_pose(self, position: np.ndarray,
                               rotation_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.cfg.camera_extrinsic_perturbation:
            pos_std = np.array(self.cfg.camera_position_std)
            rot_std = np.array(self.cfg.camera_rotation_std_deg)
            position = position + self._rng.normal(0, pos_std)
            rotation_deg = rotation_deg + self._rng.normal(0, rot_std)
        return position, rotation_deg
