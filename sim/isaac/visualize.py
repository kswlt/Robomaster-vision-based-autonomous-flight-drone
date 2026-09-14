"""Visualization script for E2E-RL drone project.

Generates:
1. Drone flight trajectory (top-down + side view)
2. Synthetic depth image example
3. Evaluation metrics comparison charts
4. Noise robustness chart

Usage:
    C:\\isaacsim\\python.bat -m sim.isaac.visualize
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

from sim.common.config import load_config, repo_root
from sim.isaac.build_scene import SceneBuilder
from sim.isaac.policy_wrapper import DiffPhysPolicyWrapper


def synthetic_depth(drone_pos, target_pos, height=48, width=64):
    depth = np.full((height, width), 24.0, dtype=np.float32)
    target_dir = target_pos - drone_pos
    target_dist = np.linalg.norm(target_dir)
    if target_dist > 0.1:
        target_dir = target_dir / target_dist
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


def run_trajectory_episode(builder, policy, max_steps=300):
    """Run one episode and record full trajectory."""
    cfg = builder.cfg
    drone = builder.drone
    drone.reset()
    policy.reset()
    yaw = 0.0

    home_pos = np.array(cfg["drone"]["initial"]["position"], dtype=float)
    target_pos = np.array(cfg["armor"]["position"], dtype=float)
    arena_L = float(cfg["arena"]["official_length_m"]) / 2
    arena_W = float(cfg["arena"]["official_width_m"]) / 2

    trajectory = []
    depths = []
    dt = 1.0 / 15.0

    for step in range(max_steps):
        pos = drone.get_position()
        vel = drone.get_velocity()
        trajectory.append(pos.copy())

        # Record depth at certain intervals
        if step % 20 == 0:
            depth = synthetic_depth(pos, target_pos)
            depths.append((step, depth.copy()))

        dist = np.linalg.norm(pos - target_pos)
        if dist < 0.4:
            trajectory.append(pos.copy())
            break

        if (abs(pos[0]) > arena_L - 0.1 or abs(pos[1]) > arena_W - 0.1 or pos[2] < 0.05):
            break

        depth = synthetic_depth(pos, target_pos)
        accel, yaw_rate = policy.compute_action_with_yaw(
            depth=depth, drone_pos=pos, drone_vel=vel, drone_yaw=yaw, target_pos=target_pos
        )
        yaw += yaw_rate * dt
        yaw = policy._wrap_angle(yaw)
        drone.set_acceleration(accel)
        drone.step_dynamics(dt)
        if builder._world is not None:
            builder._world.step(render=False)

    return np.array(trajectory), depths, target_pos, home_pos


def plot_trajectory(trajectory, target_pos, home_pos, output_path):
    """Plot top-down and side view of trajectory."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Top-down view
    ax = axes[0]
    arena_L, arena_W = 14.0, 7.5
    ax.add_patch(Rectangle((-arena_L, -arena_W), 2*arena_L, 2*arena_W,
                           fill=False, edgecolor='black', linewidth=2, label='Arena boundary'))
    ax.plot(trajectory[:, 0], trajectory[:, 1], 'b-', linewidth=1.5, alpha=0.8, label='Drone trajectory')
    ax.plot(trajectory[0, 0], trajectory[0, 1], 'go', markersize=12, label='HOME (start)')
    ax.plot(target_pos[0], target_pos[1], 'r*', markersize=20, label='ArmorTarget')
    ax.plot(trajectory[-1, 0], trajectory[-1, 1], 'rx', markersize=12, markeredgewidth=3, label='Impact point')
    ax.set_xlabel('X (m)', fontsize=12)
    ax.set_ylabel('Y (m)', fontsize=12)
    ax.set_title('Top-Down View: Drone Flight Trajectory', fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-15, 15)
    ax.set_ylim(-8, 8)

    # Side view (X-Z)
    ax = axes[1]
    ax.plot(trajectory[:, 0], trajectory[:, 2], 'b-', linewidth=1.5, alpha=0.8, label='Drone trajectory')
    ax.plot(trajectory[0, 0], trajectory[0, 2], 'go', markersize=12, label='HOME (start)')
    ax.plot(target_pos[0], target_pos[2], 'r*', markersize=20, label='ArmorTarget')
    ax.plot(trajectory[-1, 0], trajectory[-1, 2], 'rx', markersize=12, markeredgewidth=3, label='Impact point')
    ax.axhline(y=0, color='brown', linewidth=2, label='Ground')
    ax.set_xlabel('X (m)', fontsize=12)
    ax.set_ylabel('Z (m)', fontsize=12)
    ax.set_title('Side View: Altitude Profile', fontsize=14)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-13, 5)
    ax.set_ylim(-0.5, 4)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[VIZ] Trajectory plot saved: {output_path}")


def plot_depth_example(depths, output_path):
    """Plot example depth images at different timesteps."""
    n = min(len(depths), 4)
    if n == 0:
        return
    fig, axes = plt.subplots(1, n, figsize=(4*n, 4))
    if n == 1:
        axes = [axes]
    for i in range(n):
        step, depth = depths[i]
        # Normalize for display: inverse depth like training
        inv_depth = 3.0 / np.clip(depth, 0.3, 24.0) - 0.6
        im = axes[i].imshow(inv_depth, cmap='viridis', aspect='auto', origin='upper')
        axes[i].set_title(f'Step {step}\nDepth range: [{depth.min():.2f}, {depth.max():.2f}]m', fontsize=11)
        axes[i].set_xlabel('Width (px)')
        axes[i].set_ylabel('Height (px)')
        plt.colorbar(im, ax=axes[i], fraction=0.046, pad=0.04)
    plt.suptitle('Synthetic Depth Images (Inverse Depth Normalization)', fontsize=14)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[VIZ] Depth example saved: {output_path}")


def plot_noise_comparison(output_path):
    """Plot noise robustness comparison."""
    results_dir = repo_root() / "results"
    presets = ["none", "light", "moderate", "heavy"]
    hit_rates = []
    velocities = []
    angles = []

    for preset in presets:
        f = results_dir / f"noise_eval_{preset}.json"
        if f.exists():
            with open(f) as fp:
                data = json.load(fp)
            m = data["metrics"]
            hit_rates.append(m["target_hit_rate"] * 100)
            velocities.append(m["impact_velocity_mean"])
            angles.append(m["impact_angle_mean"])
        else:
            hit_rates.append(0)
            velocities.append(0)
            angles.append(0)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # Hit rate
    axes[0].bar(presets, hit_rates, color=['green', 'blue', 'orange', 'red'], alpha=0.7)
    axes[0].set_ylabel('Hit Rate (%)', fontsize=12)
    axes[0].set_title('Target Hit Rate vs Noise Level', fontsize=14)
    axes[0].set_ylim(0, 110)
    for i, v in enumerate(hit_rates):
        axes[0].text(i, v + 2, f'{v:.0f}%', ha='center', fontsize=12, fontweight='bold')
    axes[0].grid(axis='y', alpha=0.3)

    # Impact velocity
    axes[1].bar(presets, velocities, color=['green', 'blue', 'orange', 'red'], alpha=0.7)
    axes[1].set_ylabel('Impact Velocity (m/s)', fontsize=12)
    axes[1].set_title('Impact Velocity vs Noise Level', fontsize=14)
    axes[1].axhline(y=2.0, color='red', linestyle='--', label='Target min (2 m/s)')
    axes[1].legend()
    for i, v in enumerate(velocities):
        axes[1].text(i, v + 0.05, f'{v:.2f}', ha='center', fontsize=11)
    axes[1].grid(axis='y', alpha=0.3)

    # Impact angle
    axes[2].bar(presets, angles, color=['green', 'blue', 'orange', 'red'], alpha=0.7)
    axes[2].set_ylabel('Impact Angle (degrees)', fontsize=12)
    axes[2].set_title('Impact Angle vs Noise Level\n(lower = more head-on)', fontsize=14)
    axes[2].axhline(y=30, color='green', linestyle='--', label='Good (<30°)')
    axes[2].legend()
    for i, v in enumerate(angles):
        axes[2].text(i, v + 1, f'{v:.1f}°', ha='center', fontsize=11)
    axes[2].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[VIZ] Noise comparison saved: {output_path}")


def plot_milestone_summary(output_path):
    """Plot milestone summary with key metrics."""
    milestones = ['M1\nScripted\nBaseline', 'M3\nDiffPhys\nTraining', 'M4\nIsaac\nPolicy', 'M5\nHeavy\nNoise']
    hit_rates = [100, 80.5, 100, 100]
    velocities = [1.18, 0.80, 0.84, 0.37]
    angles = [155, 41.9, 23.6, 58.1]

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    colors = ['#2196F3', '#FF9800', '#4CAF50', '#F44336']

    axes[0].bar(milestones, hit_rates, color=colors, alpha=0.8)
    axes[0].set_ylabel('Hit Rate (%)', fontsize=12)
    axes[0].set_title('Hit Rate Across Milestones', fontsize=14)
    axes[0].set_ylim(0, 115)
    for i, v in enumerate(hit_rates):
        axes[0].text(i, v + 2, f'{v:.1f}%', ha='center', fontsize=11, fontweight='bold')
    axes[0].grid(axis='y', alpha=0.3)

    axes[1].bar(milestones, velocities, color=colors, alpha=0.8)
    axes[1].set_ylabel('Impact Velocity (m/s)', fontsize=12)
    axes[1].set_title('Impact Velocity Across Milestones', fontsize=14)
    axes[1].axhline(y=2.0, color='red', linestyle='--', label='Target min 2 m/s')
    axes[1].legend()
    for i, v in enumerate(velocities):
        axes[1].text(i, v + 0.05, f'{v:.2f}', ha='center', fontsize=11)
    axes[1].grid(axis='y', alpha=0.3)

    axes[2].bar(milestones, angles, color=colors, alpha=0.8)
    axes[2].set_ylabel('Impact Angle (degrees)', fontsize=12)
    axes[2].set_title('Impact Angle Across Milestones\n(lower = better)', fontsize=14)
    axes[2].axhline(y=30, color='green', linestyle='--', label='Good <30°')
    axes[2].legend()
    for i, v in enumerate(angles):
        axes[2].text(i, v + 2, f'{v:.1f}°', ha='center', fontsize=11)
    axes[2].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[VIZ] Milestone summary saved: {output_path}")


def main():
    output_dir = repo_root() / "results" / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*60)
    print("E2E-RL Visualization Generator")
    print("="*60)

    # 1. Run trajectory episode
    print("\n[1/4] Running trajectory episode...")
    builder = SceneBuilder(headless=True)
    builder.launch()
    objects = builder.build_all()
    builder.drone = objects["drone"]
    builder.armor = objects["armor"]
    builder.arena = objects["arena"]
    builder.camera = objects["camera"]

    def _inner(cfg, *keys):
        for k in keys:
            if k in cfg:
                return cfg[k]
        return cfg

    builder.cfg = {
        "arena": _inner(builder.arena_cfg, "arena"),
        "armor": _inner(builder.armor_cfg, "armor", "armor_target"),
        "drone": _inner(builder.drone_cfg, "drone"),
        "camera": _inner(builder.camera_cfg, "depth_camera"),
    }

    ckpt_dir = repo_root() / "training" / "diffphys" / "results" / "checkpoints"
    ckpts = sorted(ckpt_dir.glob("target_impact_*.pth"))
    checkpoint_path = str(ckpts[-1]) if ckpts else None
    print(f"  Using checkpoint: {checkpoint_path}")

    policy = DiffPhysPolicyWrapper(checkpoint_path, device="cpu")
    trajectory, depths, target_pos, home_pos = run_trajectory_episode(builder, policy)
    print(f"  Trajectory: {len(trajectory)} steps, final pos: {trajectory[-1]}")
    builder.close()

    # 2. Plot trajectory
    print("\n[2/4] Generating trajectory plot...")
    plot_trajectory(trajectory, target_pos, home_pos, output_dir / "flight_trajectory.png")

    # 3. Plot depth examples
    print("\n[3/4] Generating depth examples...")
    plot_depth_example(depths, output_dir / "depth_examples.png")

    # 4. Plot noise comparison
    print("\n[4/4] Generating metrics charts...")
    plot_noise_comparison(output_dir / "noise_robustness.png")
    plot_milestone_summary(output_dir / "milestone_summary.png")

    print("\n" + "="*60)
    print(f"All visualizations saved to: {output_dir}")
    print("="*60)
    for f in sorted(output_dir.glob("*.png")):
        print(f"  - {f.name} ({f.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
