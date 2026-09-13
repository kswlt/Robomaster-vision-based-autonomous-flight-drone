"""Independent ArmorTarget collider.

CRITICAL: This is a SEPARATE object from the arena mesh.
Drone <-> ArmorTarget contact = TARGET_HIT.
Drone <-> Arena contact = WRONG_COLLISION.
"""
from __future__ import annotations

from typing import Any

import numpy as np


class ArmorTarget:
    """Independent armor plate target with its own collider and contact reporting."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["armor_target"]
        self.position = np.array(self.cfg["position"], dtype=float)
        self.normal = np.array(self.cfg["normal"], dtype=float)
        self.normal /= np.linalg.norm(self.normal)
        self.size = np.array(self.cfg["collider"]["size"], dtype=float)
        self.center_radius = self.cfg["scoring"]["center_hit_radius_m"]
        self._prim = None
        self._hit = False

    def build(self, world):
        """Add armor target as a fixed cuboid with its own collision group."""
        from omni.isaac.core.objects import FixedCuboid

        self._prim = world.scene.add(
            FixedCuboid(
                prim_path="/World/ArmorTarget",
                name="armor_target",
                position=self.position,
                scale=self.size,
                size=1.0,
                color=np.array([1.0, 0.2, 0.2]),  # red = target
                collision_group="armor_target",
            )
        )
        self._hit = False
        return self

    def reset(self):
        self._hit = False

    def mark_hit(self):
        self._hit = True

    @property
    def is_hit(self) -> bool:
        return self._hit

    def center_distance(self, point: np.ndarray) -> float:
        """Distance from a point to armor plate center."""
        return float(np.linalg.norm(point - self.position))

    def is_center_hit(self, point: np.ndarray) -> bool:
        return self.center_distance(point) <= self.center_radius

    def impact_angle_deg(self, velocity: np.ndarray) -> float:
        """Angle between impact velocity and plate normal (0 = head-on)."""
        v = velocity / (np.linalg.norm(velocity) + 1e-8)
        cos_angle = float(np.dot(v, -self.normal))  # velocity should oppose normal
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_angle)))

    def get_position(self) -> np.ndarray:
        return self.position.copy()

    def get_normal(self) -> np.ndarray:
        return self.normal.copy()
