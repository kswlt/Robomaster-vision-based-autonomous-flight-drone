"""Scripted PD controller for baseline (no neural network).

Flies drone directly toward ArmorTarget using relative target vector.
Used to validate arena scale, coordinates, physics, contact, episode reset.
"""
from __future__ import annotations

import numpy as np


class ScriptedController:
    """Simple P/PD controller that flies toward a goal position.

    Phase 1: ignores non-target obstacles. Goal is to validate the full
    pipeline from HOME -> ArmorTarget -> contact -> HIT.
    """

    def __init__(
        self,
        kp_pos: float = 2.0,
        kd_vel: float = 1.5,
        max_acc: float = 8.0,
        approach_speed: float = 5.0,
    ):
        self.kp_pos = kp_pos
        self.kd_vel = kd_vel
        self.max_acc = max_acc
        self.approach_speed = approach_speed

    def compute_action(self, drone_position: np.ndarray,
                       drone_velocity: np.ndarray,
                       goal_position: np.ndarray,
                       drone_yaw: float = 0.0) -> np.ndarray:
        """Compute [ax, ay, az, yaw_rate] in body frame."""
        # Position error in world frame
        pos_error = goal_position - drone_position
        dist = np.linalg.norm(pos_error)

        if dist < 1e-6:
            return np.zeros(4)

        # Desired velocity (proportional to position error, capped)
        desired_vel = pos_error / dist * min(self.approach_speed, dist * 2.0)

        # Acceleration = PD on velocity
        vel_error = desired_vel - drone_velocity
        acc_world = self.kp_pos * pos_error - self.kd_vel * drone_velocity
        acc_world = np.clip(acc_world, -self.max_acc, self.max_acc)

        # Rotate world acceleration to body frame
        cos_y, sin_y = np.cos(drone_yaw), np.sin(drone_yaw)
        ax_body = acc_world[0] * cos_y + acc_world[1] * sin_y
        ay_body = -acc_world[0] * sin_y + acc_world[1] * cos_y
        az_body = acc_world[2]

        # Yaw rate: turn toward goal
        goal_yaw = np.arctan2(pos_error[1], pos_error[0])
        yaw_error = self._wrap_angle(goal_yaw - drone_yaw)
        yaw_rate = np.clip(yaw_error * 2.0, -3.0, 3.0)

        return np.array([ax_body, ay_body, az_body, yaw_rate], dtype=np.float32)

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        return (angle + np.pi) % (2 * np.pi) - np.pi
