"""RMUC 2026 Arena: simplified collision geometry (floor + perimeter walls).

Phase 1: Uses box colliders for physics. STL visual mesh is optional.
The official dimensions are 28m x 15m with 2.4m walls.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from sim.common.config import asset_path


class Arena:
    """Arena with simplified box colliders.

    Floor + 4 perimeter walls as FixedCuboids.
    STL visual mesh is loaded optionally if available.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["arena"]
        self.stl_path = asset_path(self.cfg["stl_path"])
        self.scale = self.cfg["arena_scale"]
        self.z_clip = self.cfg["stray_artifact"]["clip_z_max"]
        self._prim = None
        self._colliders = []

    def build(self, world):
        """Add arena to the Isaac world."""
        from isaacsim.core.api.objects import FixedCuboid

        L = float(self.cfg["official_length_m"])   # 28
        W = float(self.cfg["official_width_m"])    # 15
        H = float(self.cfg["wall_height_m"])       # 2.4
        t = 0.2  # wall thickness

        # Floor
        floor = world.scene.add(
            FixedCuboid(
                prim_path="/World/Arena/Floor",
                name="arena_floor",
                position=np.array([0.0, 0.0, -0.05]),
                scale=np.array([L, W, 0.1]),
                size=1.0,
                color=np.array([0.2, 0.2, 0.2]),
            )
        )
        self._colliders.append(floor)

        # Four perimeter walls
        wall_specs = [
            ("/World/Arena/WallN", [0, W / 2 + t / 2, H / 2], [L, t, H]),
            ("/World/Arena/WallS", [0, -W / 2 - t / 2, H / 2], [L, t, H]),
            ("/World/Arena/WallE", [L / 2 + t / 2, 0, H / 2], [t, W, H]),
            ("/World/Arena/WallW", [-L / 2 - t / 2, 0, H / 2], [t, W, H]),
        ]
        for path, pos, scale in wall_specs:
            wall = world.scene.add(
                FixedCuboid(
                    prim_path=path,
                    name=path.split("/")[-1],
                    position=np.array(pos, dtype=float),
                    scale=np.array(scale, dtype=float),
                    size=1.0,
                    color=np.array([0.3, 0.3, 0.35]),
                )
            )
            self._colliders.append(wall)

        # Try to add STL visual (optional, non-critical for phase 1)
        self._try_add_stl_visual()
        return self

    def _try_add_stl_visual(self):
        """Attempt to add STL as visual reference. Fail silently if unavailable."""
        try:
            from isaacsim.core.api.utils.stage import add_reference_to_stage
            add_reference_to_stage(str(self.stl_path), "/World/Arena/STL")
            self._prim = True
        except Exception:
            try:
                from omni.isaac.core.utils.stage import add_reference_to_stage
                add_reference_to_stage(str(self.stl_path), "/World/Arena/STL")
                self._prim = True
            except Exception:
                pass  # STL visual not critical for physics baseline

    def get_colliders(self):
        return self._colliders

    def get_prim(self):
        return self._prim
