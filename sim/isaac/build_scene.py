"""Isaac Sim scene builder.

Assembles /World with Arena, ArmorTarget, Drone, Sensors/DepthCamera.
All geometry comes from configs/*.yaml.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sim.common.config import load_config, repo_root


class SceneBuilder:
    """Build the complete Isaac Sim world from configs."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.arena_cfg = load_config("arena")
        self.armor_cfg = load_config("armor")
        self.drone_cfg = load_config("drone")
        self.camera_cfg = load_config("depth_camera")
        self.eval_cfg = load_config("evaluation")
        self._app = None
        self._world = None

    def launch(self):
        """Launch SimulationApp and create World. Must be called before imports."""
        from isaacsim import SimulationApp

        self._app = SimulationApp({"headless": self.headless})
        from isaacsim.core.api.world import World

        self._world = World(stage_units_in_meters=1.0)
        self._world.scene.add_default_ground_plane()
        self._setup_lighting()
        return self._world

    def _setup_lighting(self):
        """Add good lighting to the scene."""
        try:
            from pxr import UsdLux, Sdf, Gf
            import omni.usd

            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return

            # Dome light (ambient / environment light)
            dome_path = "/World/Lights/DomeLight"
            if not stage.GetPrimAtPath(dome_path).IsValid():
                dome = UsdLux.DomeLight.Define(stage, dome_path)
                dome.CreateIntensityAttr(1000.0)
                dome.CreateTextureFormatAttr("latlong")
                # Use a neutral gradient or solid color dome
                dome.CreateColorAttr(Gf.Vec3f(0.85, 0.88, 0.95))
                dome.CreateEnableColorTemperatureAttr(False)
                print("  [Lighting] Dome light added (intensity=1000)")

            # Distant light (sun-like directional light)
            sun_path = "/World/Lights/Sun"
            if not stage.GetPrimAtPath(sun_path).IsValid():
                sun = UsdLux.DistantLight.Define(stage, sun_path)
                sun.CreateIntensityAttr(3000.0)
                sun.CreateColorAttr(Gf.Vec3f(1.0, 0.98, 0.95))
                sun.CreateAngleAttr(2.0)
                # Position and rotate to shine down at an angle
                from pxr import UsdGeom
                xform = UsdGeom.Xformable(sun.GetPrim())
                xform.AddTranslateOp().Set(Gf.Vec3f(0, 0, 20))
                xform.AddRotateXYZOp().Set(Gf.Vec3f(-45, 0, 30))
                print("  [Lighting] Sun light added (intensity=3000, angle=-45,30)")

            # Extra fill light from opposite side
            fill_path = "/World/Lights/Fill"
            if not stage.GetPrimAtPath(fill_path).IsValid():
                fill = UsdLux.DistantLight.Define(stage, fill_path)
                fill.CreateIntensityAttr(800.0)
                fill.CreateColorAttr(Gf.Vec3f(0.9, 0.92, 1.0))
                from pxr import UsdGeom
                xform = UsdGeom.Xformable(fill.GetPrim())
                xform.AddTranslateOp().Set(Gf.Vec3f(0, 0, 15))
                xform.AddRotateXYZOp().Set(Gf.Vec3f(-60, 0, -150))
                print("  [Lighting] Fill light added (intensity=800)")

        except Exception as e:
            print(f"  [Lighting] Warning: {e}")

    def build_all(self):
        """Build arena, armor target, drone, camera in order."""
        if self._world is None:
            self.launch()

        arena = self._build_arena()
        armor = self._build_armor_target()
        drone = self._build_drone()
        camera = self._build_depth_camera(drone)
        return {"arena": arena, "armor": armor, "drone": drone, "camera": camera}

    def _build_arena(self):
        from sim.isaac.arena import Arena

        arena = Arena(self.arena_cfg)
        arena.build(self._world)
        return arena

    def _build_armor_target(self):
        from sim.isaac.armor_target import ArmorTarget

        armor = ArmorTarget(self.armor_cfg)
        armor.build(self._world)
        return armor

    def _build_drone(self):
        from sim.isaac.drone import Drone

        drone = Drone(self.drone_cfg)
        drone.build(self._world)
        return drone

    def _build_depth_camera(self, drone):
        from sim.isaac.depth_camera import DepthCamera

        cam = DepthCamera(self.camera_cfg, drone)
        cam.build(self._world)
        return cam

    def step(self, render: bool = True):
        self._world.step(render=render)

    def close(self):
        if self._app is not None:
            self._app.close()
