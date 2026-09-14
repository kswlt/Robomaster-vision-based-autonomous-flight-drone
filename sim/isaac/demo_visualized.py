"""GUI demo with real-time policy visualization using OpenCV.

Shows alongside Isaac Sim window:
  - Depth image (what the policy sees, 64x48 inverse depth)
  - State vector (velocity, target vector, gravity, GRU hidden)
  - Policy output (acceleration + yaw rate)
  - Flight trajectory top-down view

Usage:
    C:\\isaacsim\\python.bat -m sim.isaac.demo_visualized
    C:\\isaacsim\\python.bat -m sim.isaac.demo_visualized --episodes 3
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Use WebAgg backend - renders in browser, no tkinter/OpenCV GUI needed
import matplotlib
matplotlib.use('WebAgg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from sim.common.config import repo_root
from sim.isaac.build_scene import SceneBuilder
from sim.isaac.policy_wrapper import DiffPhysPolicyWrapper


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
    """Real-time matplotlib visualization (WebAgg backend, shows in browser)."""

    def __init__(self):
        self.fig = plt.figure(figsize=(14, 9))
        self.fig.suptitle('E2E-RL Policy Visualization - Depth + DiffPhys CNN+GRU',
                          fontsize=14, fontweight='bold')

        gs = GridSpec(2, 3, figure=self.fig, hspace=0.35, wspace=0.3)

        # Depth image
        self.ax_depth = self.fig.add_subplot(gs[0, 0])
        self.ax_depth.set_title('Depth Input (64x48, inverse depth)', fontsize=10)
        self.depth_im = self.ax_depth.imshow(
            np.zeros((48, 64)), cmap='viridis', vmin=0, vmax=1, origin='lower'
        )
        self.ax_depth.set_xlabel('x (pix)')
        self.ax_depth.set_ylabel('y (pix)')
        plt.colorbar(self.depth_im, ax=self.ax_depth, fraction=0.046, label='norm depth')

        # State vector
        self.ax_state = self.fig.add_subplot(gs[0, 1])
        self.ax_state.set_title('State Vector (10-dim)', fontsize=10)
        self.ax_state.axis('off')
        self.state_text = self.ax_state.text(0.05, 0.95, '', transform=self.ax_state.transAxes,
                                              fontsize=9, va='top', family='monospace')

        # Policy output
        self.ax_action = self.fig.add_subplot(gs[0, 2])
        self.ax_action.set_title('Policy Output', fontsize=10)
        self.ax_action.axis('off')
        self.action_text = self.ax_action.text(0.05, 0.95, '', transform=self.ax_action.transAxes,
                                                fontsize=9, va='top', family='monospace')

        # Trajectory
        self.ax_traj = self.fig.add_subplot(gs[1, :])
        self.ax_traj.set_title('Flight Trajectory (top-down)', fontsize=10)
        self.ax_traj.set_xlim(-15, 15)
        self.ax_traj.set_ylim(-8, 8)
        self.ax_traj.set_aspect('equal')
        self.ax_traj.grid(True, alpha=0.3)
        self.ax_traj.set_xlabel('X (m)')
        self.ax_traj.set_ylabel('Y (m)')
        self.ax_traj.plot([-14, 14, 14, -14, -14], [-7.5, -7.5, 7.5, 7.5, -7.5],
                          'k-', lw=2, label='Arena wall')
        self.ax_traj.plot(-12, -6, 'go', ms=12, label='HOME', zorder=5)
        self.ax_traj.plot(3.08, 3.84, 'r*', ms=15, label='Armor Target', zorder=5)
        self.traj_line, = self.ax_traj.plot([], [], 'b-', lw=1.5, alpha=0.8, label='Drone path')
        self.drone_point, = self.ax_traj.plot([], [], 'bo', ms=8, zorder=5)
        self.ax_traj.legend(loc='lower left', fontsize=8)

        self.trajectory = []
        self.fig.canvas.draw()
        print("\n" + "=" * 60)
        print("Visualization ready! Open this URL in your browser:")
        print(f"  http://127.0.0.1:{matplotlib.rcParams['webagg.port']}")
        print("(The browser should open automatically)")
        print("=" * 60 + "\n")
        self.fig.show()

    def update(self, depth_norm, state_dict, action_dict, pos, step, episode):
        # Depth
        self.depth_im.set_data(depth_norm)

        # State text
        v = state_dict['vel']
        t = state_dict['target']
        g = state_dict['gravity']
        self.state_text.set_text(
            f"local_vel:   [{v[0]:+6.2f}, {v[1]:+6.2f}, {v[2]:+6.2f}] m/s\n"
            f"target_vec:  [{t[0]:+6.2f}, {t[1]:+6.2f}, {t[2]:+6.2f}] m\n"
            f"gravity_dir: [{g[0]:+6.2f}, {g[1]:+6.2f}, {g[2]:+6.2f}]\n"
            f"margin:      {state_dict['margin']:.3f} m\n"
            f"\nspeed:       {state_dict['speed']:.2f} m/s\n"
            f"dist2target: {state_dict['dist']:.2f} m\n"
            f"altitude:    {pos[2]:.2f} m\n"
            f"GRU hidden:  {state_dict['hidden_norm']:.3f} (L2)"
        )

        # Action text
        a = action_dict['accel']
        self.action_text.set_text(
            f"accel_x:  {a[0]:+7.3f} m/s^2\n"
            f"accel_y:  {a[1]:+7.3f} m/s^2\n"
            f"accel_z:  {a[2]:+7.3f} m/s^2\n"
            f"yaw_rate: {action_dict['yaw']:+7.3f} rad/s\n"
            f"\nthrust_mag: {action_dict['thrust_mag']:.3f}\n"
            f"\n-> Drone dynamics\n-> Flight controller"
        )

        # Trajectory
        self.trajectory.append((pos[0], pos[1]))
        if len(self.trajectory) > 800:
            self.trajectory = self.trajectory[-800:]
        xs, ys = zip(*self.trajectory)
        self.traj_line.set_data(xs, ys)
        self.drone_point.set_data([pos[0]], [pos[1]])

        self.fig.canvas.draw_idle()

    def reset_trajectory(self):
        self.trajectory = []
        self.traj_line.set_data([], [])

    def close(self):
        plt.close(self.fig)


def run_visualized_demo(episodes=2):
    """Run demo with real-time policy visualization."""
    print("=" * 60)
    print("E2E-RL Policy Visualization Demo (OpenCV)")
    print("=" * 60)
    print("\nTwo windows will open:")
    print("  1. Isaac Sim - 3D scene with drone flying")
    print("  2. OpenCV    - depth image, state, action, trajectory")
    print("\nLaunching Isaac Sim... (~30 seconds)")

    # Build scene
    builder = SceneBuilder(headless=False)
    builder.launch()
    objects = builder.build_all()
    drone = objects["drone"]
    armor = objects["armor"]
    world = builder._world

    home_pos = drone.init_pos.copy()
    target_pos = armor.position.copy()

    # Load policy
    ckpt_dir = repo_root() / "training" / "diffphys" / "results" / "checkpoints"
    ckpts = sorted(ckpt_dir.glob("target_impact_*.pth"))
    policy = DiffPhysPolicyWrapper(str(ckpts[-1]), device="cpu")
    print(f"Loaded policy: {ckpts[-1].name}")

    # Create visualizer
    viz = PolicyVisualizer()

    dt = 1.0 / 15.0
    total_hits = 0

    try:
        for ep in range(episodes):
            print(f"\n--- Episode {ep+1}/{episodes} ---")
            drone.reset()
            policy.reset()
            viz.reset_trajectory()
            step = 0

            while step < 300:
                pos = drone.get_position()
                vel = drone.get_velocity()

                # Check hit
                if armor.center_distance(pos) < 0.4:
                    total_hits += 1
                    impact_speed = float(np.linalg.norm(vel))
                    print(f"  TARGET HIT at step {step}! speed={impact_speed:.3f} m/s")
                    # Show hit frame
                    for _ in range(30):
                        world.step(render=True)
                    break

                # Generate depth
                depth = synthetic_depth(pos, target_pos)

                # Policy inference
                yaw = drone._yaw if hasattr(drone, '_yaw') else 0.0
                action = policy.compute_action_with_yaw(depth, pos, vel, yaw, target_pos)
                accel = np.asarray(action[0], dtype=np.float64)
                yaw_rate = action[1] if action[1] is not None else 0.0

                # Apply action
                drone.set_acceleration(accel)
                drone.step_dynamics(dt)
                if yaw_rate is not None:
                    drone._yaw = yaw + float(yaw_rate) * dt

                # Normalize depth for display
                depth_norm = 3.0 / np.clip(depth, 0.3, 24.0) - 0.6
                depth_norm = np.clip(depth_norm, 0, 1)

                # State dict
                target_vec = target_pos - pos
                dist = np.linalg.norm(target_vec)
                speed = np.linalg.norm(vel)
                hidden_norm = float(np.linalg.norm(policy._hidden.numpy())) if hasattr(policy, '_hidden') else 0.0

                state_dict = {
                    'vel': vel,
                    'target': target_vec,
                    'gravity': np.array([0, 0, -1.0]),
                    'margin': 0.2,
                    'speed': speed,
                    'dist': dist,
                    'hidden_norm': hidden_norm,
                }

                action_dict = {
                    'accel': accel,
                    'yaw': float(yaw_rate) if yaw_rate else 0.0,
                    'thrust_mag': float(np.linalg.norm(accel)),
                }

                # Update visualization
                viz.update(depth_norm, state_dict, action_dict, pos, step, ep + 1)

                world.step(render=True)
                step += 1

                if step % 20 == 0:
                    print(f"  step={step:3d} pos=[{pos[0]:5.1f},{pos[1]:5.1f},{pos[2]:4.1f}] "
                          f"dist={dist:5.1f}m vel={speed:4.1f}m/s")

            if step >= 300:
                print(f"  TIMEOUT at step {step}")

        print(f"\n{'='*60}")
        print(f"Demo complete. Hits: {total_hits}/{episodes}")
        print(f"{'='*60}")
        print("\nClose both windows to exit.")

        # Keep windows open
        while True:
            world.step(render=True)
    except KeyboardInterrupt:
        pass
    finally:
        viz.close()
        builder.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=2)
    args = parser.parse_args()
    run_visualized_demo(episodes=args.episodes)
