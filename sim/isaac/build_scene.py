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
        from omni.isaac.core import World

        self._world = World(stage_units_in_meters=1.0)
        self._world.scene.add_default_ground_plane()
        return self._world

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
