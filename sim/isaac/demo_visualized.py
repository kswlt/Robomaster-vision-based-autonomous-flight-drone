"""GUI demo with real-time policy visualization via shared file.

Isaac Sim process writes visualization data to results/vis_data.npz.
A separate system Python process (vis_viewer.py) reads it and shows
an OpenCV window with depth, state, action, and trajectory.

Usage (two terminals):
  Terminal 1 (Isaac Sim):
    C:\\isaacsim\\python.bat -m sim.isaac.demo_visualized --episodes 10
  Terminal 2 (visualization):
    python sim/isaac/vis_viewer.py
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sim.common.config import repo_root
from sim.isaac.build_scene import SceneBuilder
from sim.isaac.policy_wrapper import DiffPhysPolicyWrapper

VIS_DATA_PATH = REPO_ROOT / "results" / "vis_data.npz"


def synthetic_depth(drone_pos, target_pos, height=48, width=64):
    """Generate synthetic depth image matching DiffPhys training input."""
    depth = np.full((height, width), 24.0, dtype=np.float32)
    target_dir = target_pos - drone_pos
    target_dist = np.linalg.norm(target_dir)
    if target_dist > 0.1:
        cy, cx = height // 2, width // 2
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                y, x = cy + dy, cx + dx
                if 0 <= y < height and 0 <= x < width:
                    depth[y, x] = target_dist
    floor_depth = drone_pos[2]
    if floor_depth > 0.3:
        depth[height // 2:, :] = np.minimum(depth[height // 2:, :], floor_depth)
    return depth


class PolicyVisualizer:
    """Writes visualization data to shared npz file for vis_viewer.py."""

    def __init__(self):
        self.trajectory = []
        VIS_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Write initial empty frame
        self._write(
            depth=np.zeros((48, 64), dtype=np.float32),
            state=np.zeros(10, dtype=np.float32),
            action=np.zeros(6, dtype=np.float32),
            pos=np.zeros(3, dtype=np.float32),
            step=0, episode=0, status="starting",
            hidden_norm=0.0,
        )
        print(f"\n  [Visualizer] Writing data to {VIS_DATA_PATH}")
        print(f"  [Visualizer] Run this in another terminal to see the panel:")
        print(f"    python sim/isaac/vis_viewer.py\n")

    def _write(self, depth, state, action, pos, step, episode, status, hidden_norm):
        traj = np.array(self.trajectory[-500:], dtype=np.float32) if self.trajectory else np.zeros((0, 2), dtype=np.float32)
        np.savez_compressed(
            VIS_DATA_PATH,
            depth=depth.astype(np.float32),
            state=state.astype(np.float32),
            action=action.astype(np.float32),
            pos=pos.astype(np.float32),
            trajectory=traj,
            step=np.int32(step),
            episode=np.int32(episode),
            status=np.array(status),
            hidden_norm=np.float32(hidden_norm),
            timestamp=np.float64(time.time()),
        )

    def update(self, depth_norm, state_dict, action_dict, pos, step, episode):
        state_vec = np.array([
            *state_dict['vel'], *state_dict['target'], *state_dict['gravity'], state_dict['margin']
        ], dtype=np.float32)
        action_vec = np.array([
            *action_dict['accel'], action_dict['yaw'], action_dict['thrust_mag'], 0.0
        ], dtype=np.float32)

        self.trajectory.append([pos[0], pos[1]])
        self._write(
            depth=depth_norm, state=state_vec, action=action_vec,
            pos=np.array(pos, dtype=np.float32),
            step=step, episode=episode, status="running",
            hidden_norm=state_dict.get('hidden_norm', 0.0),
        )

    def reset_trajectory(self):
        self.trajectory = []

    def close(self):
        self._write(
            depth=np.zeros((48, 64), dtype=np.float32),
            state=np.zeros(10, dtype=np.float32),
            action=np.zeros(6, dtype=np.float32),
            pos=np.zeros(3, dtype=np.float32),
            step=0, episode=0, status="finished",
            hidden_norm=0.0,
        )


def run_visualized_demo(episodes=3, speed=1.0):
    builder = SceneBuilder(headless=False)
    world = builder.launch()
    objects = builder.build_all()

    arena = objects['arena']
    armor = objects['armor']
    drone = objects['drone']
    camera = objects['camera']

    policy = DiffPhysPolicyWrapper(
        checkpoint_path=str(repo_root() / "training/diffphys/results/checkpoints/target_impact_0006k.pth")
    )

    world.reset()

    viz = PolicyVisualizer()

    HOME = np.array([-12.0, -6.0, 0.3])
    TARGET = np.array([3.08, 3.84, 1.5])
    DT = 1/60
    MAX_STEPS = 600

    total_hits = 0

    for ep in range(episodes):
        print(f"\n--- Episode {ep+1}/{episodes} ---")
        # Reset drone to HOME
        drone._position = HOME.copy()
        drone._velocity = np.zeros(3)
        if drone._prim is not None:
            drone._prim.set_world_pose(position=HOME)
            drone._prim.set_linear_velocity(np.zeros(3))
        policy.reset()
        viz.reset_trajectory()
        builder.step(render=True)

        hit = False
        for step in range(MAX_STEPS):
            pos = drone.get_position()
            vel = drone.get_velocity()
            yaw = drone._yaw

            depth_raw = synthetic_depth(pos, TARGET)

            # Compute policy action (world-frame accel + yaw_rate)
            accel, yaw_rate = policy.compute_action_with_yaw(
                depth_raw, pos, vel, yaw, TARGET
            )

            # Build visualization data manually (matches training preprocessing)
            depth_t = torch.from_numpy(depth_raw).float()
            depth_norm_raw = (3.0 / depth_t.clamp(0.3, 24.0) - 0.6).numpy()
            # For display, show the 12x16 pooled version upscaled
            depth_pooled = F.max_pool2d(
                depth_t.unsqueeze(0).unsqueeze(0), 4, 4
            ).squeeze().numpy()
            depth_display = np.repeat(np.repeat(depth_pooled, 4, axis=0), 4, axis=1)

            # Body frame state for display
            fwd = np.array([np.cos(yaw), np.sin(yaw), 0.0])
            right = np.cross([0, 0, 1], fwd)
            R = np.column_stack([fwd, right, [0, 0, 1]])
            local_v = vel @ R
            target_v_raw = TARGET - pos
            target_v_norm = np.linalg.norm(target_v_raw)
            target_v_unit = target_v_raw / (target_v_norm + 1e-8)
            target_v = target_v_unit * min(target_v_norm, policy.max_speed)
            target_v_body = target_v @ R

            state_dict = {
                'vel': local_v,
                'target': target_v_body,
                'gravity': np.array([0.0, 0.0, 1.0]),
                'margin': policy.margin,
                'speed': float(np.linalg.norm(vel)),
                'dist': float(target_v_norm),
                'hidden_norm': 0.0,  # not exposed by wrapper
            }
            action_dict = {
                'accel': accel,
                'yaw': yaw_rate,
                'thrust_mag': float(np.linalg.norm(accel)),
            }

            viz.update(depth_display, state_dict, action_dict, pos, step, ep + 1)

            # Apply policy acceleration
            drone.set_acceleration(accel)
            drone.step_dynamics(DT)
            drone._yaw += yaw_rate * DT

            if step % 20 == 0:
                print(f"  step={step:3d} pos=[{pos[0]:5.1f},{pos[1]:5.1f},{pos[2]:4.1f}] "
                      f"dist={np.linalg.norm(TARGET-pos):5.1f}m vel={np.linalg.norm(vel):.1f}m/s")

            builder.step(render=True)

            if drone.check_hit(TARGET, threshold=0.5):
                hit = True
                total_hits += 1
                print(f"  TARGET HIT at step {step}! speed={np.linalg.norm(vel):.3f} m/s")
                for _ in range(30):
                    builder.step(render=True)
                break

        if not hit:
            print(f"  TIMEOUT at step {MAX_STEPS}")

    print(f"\n{'='*60}")
    print(f"Demo complete. Hits: {total_hits}/{episodes}")
    print(f"{'='*60}")
    print("\nClose Isaac Sim window to exit.")
    print("Visualization panel (vis_viewer.py) will show 'finished' status.")

    while True:
        builder.step(render=True)

    builder.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    run_visualized_demo(episodes=args.episodes, speed=args.speed)
