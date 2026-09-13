"""Simplified rigid-body drone with high-level control interface.

Phase 1: no 4-motor aerodynamics. Velocity/acceleration control aligned
with DiffPhys action definition [ax, ay, az, yaw_rate].
"""
from __future__ import annotations

from typing import Any

import numpy as np


class Drone:
    """Simplified quadrotor rigid body.

    Unified interface:
        reset()
        step(action)
        get_state()
        get_observation()
        get_depth()  (via attached camera)
        get_relative_goal(goal_pos)
        check_hit(armor)
        check_wrong_collision(arena_contacts)
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["drone"]
        self.mass = self.cfg["mass_kg"]
        self.max_vel = self.cfg["max_velocity_mps"]
        self.max_acc = self.cfg["max_acceleration_mps2"]
        self.max_yaw_rate = np.deg2rad(self.cfg["max_yaw_rate_dps"])
        self.radius = self.cfg["collider"]["radius_m"]
        self.init_pos = np.array(self.cfg["initial"]["position"], dtype=float)
        self.init_yaw = np.deg2rad(self.cfg["initial"]["yaw_deg"])
        self._prim = None
        self._position = self.init_pos.copy()
        self._velocity = np.zeros(3)
        self._yaw = self.init_yaw

    def build(self, world):
        """Add drone as dynamic sphere."""
        from isaacsim.core.api.objects import DynamicSphere

        self._prim = world.scene.add(
            DynamicSphere(
                prim_path="/World/Drone",
                name="drone",
                position=self.init_pos,
                radius=self.radius,
                mass=self.mass,
                color=np.array([0.2, 0.6, 1.0]),
            )
        )
        return self

    def reset(self):
        """Reset to initial state."""
        if self._prim is not None:
            self._prim.set_world_pose(position=self.init_pos)
            self._prim.set_linear_velocity(np.zeros(3))
            self._prim.set_angular_velocity(np.zeros(3))
        self._position = self.init_pos.copy()
        self._velocity = np.zeros(3)
        self._yaw = self.init_yaw

    def step(self, action: np.ndarray):
        """Apply high-level action [ax, ay, az, yaw_rate] in body frame.

        Simple kinematic integration for phase 1 (no full aerodynamics).
        Action is clipped to configured limits.
        """
        ax, ay, az, yaw_rate = action
        ax = float(np.clip(ax, -self.max_acc, self.max_acc))
        ay = float(np.clip(ay, -self.max_acc, self.max_acc))
        az = float(np.clip(az, -self.max_acc, self.max_acc))
        yaw_rate = float(np.clip(yaw_rate, -self.max_yaw_rate, self.max_yaw_rate))

        dt = 0.02  # matches config dt

        # Rotate body-frame acceleration to world frame
        cos_y, sin_y = np.cos(self._yaw), np.sin(self._yaw)
        acc_world = np.array([
            ax * cos_y - ay * sin_y,
            ax * sin_y + ay * cos_y,
            az,
        ])

        self._velocity += acc_world * dt
        speed = np.linalg.norm(self._velocity)
        if speed > self.max_vel:
            self._velocity = self._velocity / speed * self.max_vel
        self._position += self._velocity * dt
        self._yaw += yaw_rate * dt

        if self._prim is not None:
            self._prim.set_world_pose(position=self._position)
            self._prim.set_linear_velocity(self._velocity)

    def get_state(self) -> dict:
        return {
            "position": self._position.copy(),
            "velocity": self._velocity.copy(),
            "yaw": self._yaw,
            "gravity_vector": np.array([0.0, 0.0, -1.0]),  # in body frame (level flight)
        }

    def get_observation(self, goal_pos: np.ndarray) -> dict:
        """Full policy observation: state + relative goal."""
        state = self.get_state()
        rel_goal = goal_pos - self._position
        return {
            "relative_goal": rel_goal,
            "velocity": state["velocity"],
            "gravity_vector": state["gravity_vector"],
            "angular_velocity": np.zeros(3),  # simplified
        }

    def get_relative_goal(self, goal_pos: np.ndarray) -> np.ndarray:
        return goal_pos - self._position

    def get_position(self) -> np.ndarray:
        return self._position.copy()

    def get_velocity(self) -> np.ndarray:
        return self._velocity.copy()

    def check_hit(self, armor_position: np.ndarray, threshold: float = 0.3) -> bool:
        """Check if drone is in contact with armor target."""
        return float(np.linalg.norm(self._position - armor_position)) < threshold

    def check_wrong_collision(self, arena_contact: bool) -> bool:
        return arena_contact
