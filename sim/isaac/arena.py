"""RMUC 2026 Arena: real STL visual mesh + simplified box colliders.

Loads the actual RoboMaster 2026 battlefield STL as visual geometry,
while using box colliders (floor + perimeter walls) for physics.
STL unit = meters (calibrated against official 28m x 15m battlefield).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from sim.common.config import asset_path


class Arena:
    """Arena with real STL visual and simplified box colliders.

    Visual: high-poly STL mesh of the actual RMUC 2026 battlefield.
    Physics: floor + 4 perimeter walls as FixedCuboids (fast, stable).
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg["arena"]
        self.stl_path = asset_path(self.cfg["stl_path"])
        self.scale = float(self.cfg["arena_scale"])
        self.z_clip = float(self.cfg["stray_artifact"]["clip_z_max"])
        self._prim = None
        self._colliders = []
        self._stl_loaded = False

    def build(self, world):
        """Add arena to the Isaac world: colliders + STL visual."""
        from isaacsim.core.api.objects import FixedCuboid

        L = float(self.cfg["official_length_m"])   # 28
        W = float(self.cfg["official_width_m"])    # 15
        H = float(self.cfg["wall_height_m"])       # 2.4
        t = 0.2  # wall thickness

        # --- Physics colliders (simplified boxes) ---
        # Floor
        floor = world.scene.add(
            FixedCuboid(
                prim_path="/World/Arena/Floor",
                name="arena_floor",
                position=np.array([0.0, 0.0, -0.05]),
                scale=np.array([L, W, 0.1]),
                size=1.0,
                color=np.array([0.15, 0.15, 0.15]),
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
                    color=np.array([0.25, 0.25, 0.30]),
                )
            )
            self._colliders.append(wall)

        # --- Real STL visual mesh ---
        self._load_stl_visual(world)
        return self

    def _load_stl_visual(self, world):
        """Load the real RMUC STL as visual-only geometry (no collider)."""
        stl_path = Path(self.stl_path)
        if not stl_path.exists():
            print(f"  [Arena] WARNING: STL not found at {stl_path}")
            return

        print(f"  [Arena] Loading STL visual: {stl_path.name}")
        print(f"  [Arena]   scale={self.scale}, z_clip={self.z_clip}")

        try:
            # Method 1: add_reference_to_stage (Isaac Sim supports STL import)
            from isaacsim.core.api.utils.stage import add_reference_to_stage
            add_reference_to_stage(str(stl_path), "/World/Arena/STL")
            self._apply_stl_transform("/World/Arena/STL")
            self._stl_loaded = True
            print(f"  [Arena] STL visual loaded successfully (method: add_reference)")
            return
        except Exception as e:
            print(f"  [Arena] add_reference failed: {e}")

        try:
            # Method 2: omni.isaac.core.utils.stage (older API)
            from omni.isaac.core.utils.stage import add_reference_to_stage
            add_reference_to_stage(str(stl_path), "/World/Arena/STL")
            self._apply_stl_transform("/World/Arena/STL")
            self._stl_loaded = True
            print(f"  [Arena] STL visual loaded successfully (method: omni.isaac)")
            return
        except Exception as e:
            print(f"  [Arena] omni.isaac add_reference failed: {e}")

        # Method 3: build mesh from trimesh vertices/faces
        try:
            self._load_stl_via_trimesh(world)
            self._stl_loaded = True
            print(f"  [Arena] STL visual loaded successfully (method: trimesh)")
            return
        except Exception as e:
            print(f"  [Arena] trimesh method failed: {e}")
            import traceback
            traceback.print_exc()

        print(f"  [Arena] WARNING: All STL load methods failed. Using boxes only.")

    def _apply_stl_transform(self, prim_path):
        """Apply scale and position to the loaded STL prim."""
        try:
            from pxr import UsdGeom, Gf
            stage = None
            # Get stage from the current context
            import omni.usd
            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return

            prim = stage.GetPrimAtPath(prim_path)
            if not prim.IsValid():
                # Try to find the STL prim (may be created as child)
                print(f"  [Arena] Prim {prim_path} not valid, searching...")
                return

            xform = UsdGeom.Xformable(prim)
            # Set scale
            scale_attr = xform.GetScaleAttr()
            if not scale_attr.HasValue():
                scale_attr = xform.AddScaleOp()
            scale_attr.Set(Gf.Vec3f(self.scale, self.scale, self.scale))

            # STL is already centered at origin, position = [0,0,0]
            translate_attr = xform.GetTranslateAttr()
            if not translate_attr.HasValue():
                translate_attr = xform.AddTranslateOp()
            translate_attr.Set(Gf.Vec3f(0.0, 0.0, 0.0))

            print(f"  [Arena] STL transform applied: scale={self.scale}")
        except Exception as e:
            print(f"  [Arena] STL transform warning: {e}")

    def _load_stl_via_trimesh(self, world):
        """Load STL via trimesh and create Isaac Sim mesh prim."""
        import trimesh
        from pxr import UsdGeom, Gf, Vt, Sdf, Usd
        import omni.usd

        # Read STL
        mesh = trimesh.load(str(self.stl_path))
        if isinstance(mesh, trimesh.Scene):
            # Merge all geometries
            mesh = trimesh.util.concatenate(
                [g for g in mesh.geometry.values() if hasattr(g, 'vertices')]
            )

        vertices = np.array(mesh.vertices, dtype=np.float32) * self.scale
        faces = np.array(mesh.faces, dtype=np.int32)

        print(f"  [Arena] STL raw: {len(vertices)} verts, {len(faces)} faces, "
              f"z=[{vertices[:,2].min():.2f}, {vertices[:,2].max():.2f}]")

        # Clip stray artifacts above z_clip (remove vertices and orphaned faces)
        if self.z_clip > 0 and vertices[:, 2].max() > self.z_clip:
            valid_mask = vertices[:, 2] <= self.z_clip
            # Keep faces where ALL 3 vertices are valid
            face_valid = valid_mask[faces].all(axis=1)
            faces = faces[face_valid]
            # Remap vertex indices
            valid_idx = np.where(valid_mask)[0]
            idx_map = np.full(len(vertices), -1, dtype=np.int32)
            idx_map[valid_idx] = np.arange(len(valid_idx))
            faces = idx_map[faces]
            vertices = vertices[valid_mask]
            print(f"  [Arena] After z_clip<={self.z_clip}: {len(vertices)} verts, {len(faces)} faces, "
                  f"z=[{vertices[:,2].min():.2f}, {vertices[:,2].max():.2f}]")

        # Simplify mesh if too many triangles (target ~15k faces for visual)
        target_faces = 15000
        if len(faces) > target_faces:
            try:
                import trimesh
                tmp_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
                simplified = tmp_mesh.simplify_quadric_decimation(target_faces)
                vertices = np.array(simplified.vertices, dtype=np.float32)
                faces = np.array(simplified.faces, dtype=np.int32)
                print(f"  [Arena] After simplify: {len(vertices)} verts, {len(faces)} faces "
                      f"(target {target_faces})")
            except Exception as e:
                print(f"  [Arena] Simplify failed ({e}), using full mesh")

        # Create mesh on stage
        stage = omni.usd.get_context().get_stage()
        if stage is None:
            raise RuntimeError("No USD stage available")

        mesh_path = "/World/Arena/STL"
        # Remove existing if any
        if stage.GetPrimAtPath(mesh_path).IsValid():
            stage.RemovePrim(mesh_path)

        usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
        usd_mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(vertices))
        usd_mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([3] * len(faces)))
        usd_mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray(faces.flatten().tolist()))

        # Set material color
        usd_mesh.CreateDisplayColorAttr().Set(
            Vt.Vec3fArray([Gf.Vec3f(0.5, 0.5, 0.55)])
        )

        print(f"  [Arena] Created USD mesh: {len(vertices)} verts, {len(faces)} faces")

    def get_colliders(self):
        return self._colliders

    def get_prim(self):
        return self._prim

    @property
    def stl_loaded(self) -> bool:
        return self._stl_loaded
