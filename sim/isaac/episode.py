"""Episode runner with mission state machine.

States: TAKEOFF -> ATTACK -> HIT -> RECOVER -> RETURN -> HOME
The state machine is NOT AI. The policy/controller handles goal-directed flight.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from sim.isaac.controller import ScriptedController


@dataclass
class EpisodeResult:
    episode_id: int
    success: bool = False
    target_hit: bool = False
    center_hit: bool = False
    wrong_collision: bool = False
    timeout: bool = False
    impact_velocity: float = 0.0
    impact_angle_deg: float = 0.0
    impact_center_error: float = 0.0
    time_to_target: float = 0.0
    recovered: bool = False
    returned_home: bool = False
    steps: int = 0


class EpisodeRunner:
    """Runs one episode: takeoff, attack, hit, recover, return."""

    STATES = ["TAKEOFF", "ATTACK", "HIT", "RECOVER", "RETURN", "HOME"]

    def __init__(self, drone, armor, camera, arena, eval_cfg: dict[str, Any]):
        self.drone = drone
        self.armor = armor
        self.camera = camera
        self.arena = arena
        self.cfg = eval_cfg["evaluation"]
        self.max_steps = self.cfg["max_steps_per_episode"]
        self.dt = self.cfg["dt"]
        self.takeoff_height = self.cfg["mission"]["takeoff_height_m"]
        self.controller = ScriptedController()
        self.home_pos = np.array(self.drone.init_pos, dtype=float)
        self.result = EpisodeResult(episode_id=0)

    def reset(self, episode_id: int = 0):
        """Reset drone, armor, state."""
        self.drone.reset()
        self.armor.reset()
        self.state = "TAKEOFF"
        self.step_count = 0
        self.start_time = time.time()
        self.result = EpisodeResult(episode_id=episode_id)
        self.hit_step = -1

    def step(self) -> EpisodeResult:
        """Advance one simulation step. Returns result when episode ends."""
        self.step_count += 1
        self.result.steps = self.step_count

        pos = self.drone.get_position()
        vel = self.drone.get_velocity()
        yaw = self.drone._yaw

        if self.state == "TAKEOFF":
            goal = self.home_pos + np.array([0, 0, self.takeoff_height])
            if pos[2] >= self.takeoff_height - 0.1:
                self.state = "ATTACK"

        elif self.state == "ATTACK":
            goal = self.armor.get_position()
            # Check target hit
            if self.drone.check_hit(goal, threshold=0.4):
                self._on_hit(pos, vel)
                self.state = "HIT"

        elif self.state == "HIT":
            # Phase 1: immediately end episode on hit (prove we can hit)
            # Phase 2: continue to RECOVER
            self.result.success = True
            return self.result

        elif self.state == "RECOVER":
            goal = pos + np.array([0, 0, 1.0])  # stabilize upward
            if self.step_count - self.hit_step > 100:
                self.result.recovered = True
                self.state = "RETURN"

        elif self.state == "RETURN":
            goal = self.home_pos
            if np.linalg.norm(pos - self.home_pos) < 0.5:
                self.result.returned_home = True
                self.state = "HOME"
                self.result.success = True
                return self.result

        elif self.state == "HOME":
            self.result.success = True
            return self.result

        # Compute and apply action
        action = self.controller.compute_action(pos, vel, goal, yaw)
        self.drone.step(action)
        if self.camera is not None:
            self.camera.update()

        # Timeout check
        if self.step_count >= self.max_steps:
            self.result.timeout = True
            return self.result

        return None  # episode continues

    def _on_hit(self, pos: np.ndarray, vel: np.ndarray):
        self.armor.mark_hit()
        self.result.target_hit = True
        self.result.impact_velocity = float(np.linalg.norm(vel))
        self.result.impact_angle_deg = self.armor.impact_angle_deg(vel)
        self.result.impact_center_error = self.armor.center_distance(pos)
        self.result.center_hit = self.armor.is_center_hit(pos)
        self.result.time_to_target = time.time() - self.start_time
        self.hit_step = self.step_count

    def run(self, episode_id: int = 0) -> EpisodeResult:
        """Run full episode to completion."""
        self.reset(episode_id)
        while True:
            result = self.step()
            if result is not None:
                return result
