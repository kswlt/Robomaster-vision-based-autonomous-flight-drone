"""RMUC 2026 Arena: STL import with z-clip and simplified collision."""
from __future__ import annotations

from typing import Any

import numpy as np

from sim.common.config import asset_path


class Arena:
    """Loads the RMUC STL as visual mesh with simplified collision geometry.

    The STL is NOT watertight (124995 triangles). We use it for visual rendering
    and create simplified colliders (boxes / convex) for physics.
    Stray artifact at z > 4.0 is clipped.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["arena"]
        self.stl_path = asset_path(self.cfg["stl_path"])
        self.scale = self.cfg["arena_scale"]
        self.z_clip = self.cfg["stray_artifact"]["clip_z_max"]
        self._prim = None

    def build(self, world):
        """Add arena to the Isaac world."""
        from omni.isaac.core.utils.stage import add_reference_to_stage
        from omni.isaac.core.prims import XFormPrim
        from pxr import UsdGeom, Gf

        # Add STL reference (visual only initially)
        prim_path = "/World/Arena"
        add_reference_to_stage(self.stl_path, prim_path)

        # Apply scale and clip via XForm
        xform = XFormPrim(prim_path)
        xform.set_scale(np.array([self.scale, self.scale, self.scale]))

        self._prim = xform
        self._setup_collision(world, prim_path)
        return self

    def _setup_collision(self, world, prim_path: str):
        """Create simplified collision for the arena.

        Strategy: perimeter walls as boxes, floor as plane.
        Full triangle-mesh collision is avoided for performance.
        """
        from omni.isaac.core.objects import FixedCuboid
        import numpy as np

        L = self.cfg["official_length_m"]   # 28
        W = self.cfg["official_width_m"]    # 15
        H = self.cfg["wall_height_m"]       # 2.4
        t = 0.2  # wall thickness estimate

        # Floor
        world.scene.add(
            FixedCuboid(
                prim_path="/World/Arena/Floor",
                name="arena_floor",
                position=np.array([0.0, 0.0, -0.05]),
                scale=np.array([L, W, 0.1]),
                size=1.0,
                color=np.array([0.2, 0.2, 0.2]),
            )
        )

        # Four perimeter walls
        wall_specs = [
            ("/World/Arena/WallN", [0, W / 2 + t / 2, H / 2], [L, t, H]),
            ("/World/Arena/WallS", [0, -W / 2 - t / 2, H / 2], [L, t, H]),
            ("/World/Arena/WallE", [L / 2 + t / 2, 0, H / 2], [t, W, H]),
            ("/World/Arena/WallW", [-L / 2 - t / 2, 0, H / 2], [t, W, H]),
        ]
        for path, pos, scale in wall_specs:
            world.scene.add(
                FixedCuboid(
                    prim_path=path,
                    name=path.split("/")[-1],
                    position=np.array(pos, dtype=float),
                    scale=np.array(scale, dtype=float),
                    size=1.0,
                    color=np.array([0.3, 0.3, 0.35]),
                    collision_group="arena",
                )
            )

    def get_prim(self):
        return self._prim
