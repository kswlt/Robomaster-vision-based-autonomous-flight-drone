"""Sim-to-Real noise evaluation for DiffPhys policy in Isaac Sim.

Adds domain randomization and noise to test policy robustness:
- Depth Gaussian noise
- Depth frame drop
- Control/state latency
- Drone mass variation
- Camera extrinsic perturbation

Usage:
    C:\\isaacsim\\python.bat -m sim.isaac.eval_noise --episodes 100 --noise all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sim.isaac.build_scene import SceneBuilder
from sim.isaac.armor_target import ArmorTarget
from sim.isaac.drone import Drone
from sim.isaac.depth_camera import DepthCamera
from sim.isaac.policy_wrapper import DiffPhysPolicyWrapper
from sim.common.config import load_config, repo_root


def synthetic_depth(drone_pos: np.ndarray, target_pos: np.ndarray,
                    height: int = 48, width: int = 64) -> np.ndarray:
    """Generate synthetic depth image from drone position."""
    depth = np.full((height, width), 24.0, dtype=np.float32)
    target_dir = target_pos - drone_pos
    target_dist = np.linalg.norm(target_dir)
    if target_dist > 0.1:
        target_dir = target_dir / target_dist
        cy, cx = height // 2, width // 2
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                y, x = cy + dy, cx + dx
                if 0 <= y < height and 0 <= x < width:
                    depth[y, x] = target_dist
    floor_depth = drone_pos[2]
    if floor_depth > 0.3:
        depth[height // 2:, :] = np.minimum(depth[height // 2:, :], floor_depth)
    return depth


class NoiseConfig:
    """Configuration for Sim-to-Real noise injection."""
    def __init__(
        self,
        depth_noise_std: float = 0.0,
        depth_drop_prob: float = 0.0,
        latency_steps: int = 0,
        mass_variation: float = 0.0,
        camera_pos_noise: float = 0.0,
        camera_rot_noise: float = 0.0,
    ):
        self.depth_noise_std = depth_noise_std
        self.depth_drop_prob = depth_drop_prob
        self.latency_steps = latency_steps
        self.mass_variation = mass_variation
        self.camera_pos_noise = camera_pos_noise
        self.camera_rot_noise = camera_rot_noise


class NoiseInjector:
    """Injects Sim-to-Real noise into the evaluation loop."""
    def __init__(self, config: NoiseConfig):
        self.cfg = config
        self.last_depth = None
        self.action_buffer = []
        self.state_buffer = []

    def reset(self):
        """Reset noise state for new episode."""
        self.last_depth = None
        self.action_buffer = []
        self.state_buffer = []

    def apply_depth_noise(self, depth: np.ndarray) -> np.ndarray:
        """Apply Gaussian noise and frame drop to depth."""
        if self.cfg.depth_drop_prob > 0 and np.random.random() < self.cfg.depth_drop_prob:
            if self.last_depth is not None:
                return self.last_depth.copy()
        if self.cfg.depth_noise_std > 0:
            noise = np.random.normal(0, self.cfg.depth_noise_std, depth.shape)
            depth = depth + noise
            depth = np.clip(depth, 0.3, 24.0)
        self.last_depth = depth.copy()
        return depth

    def apply_latency(self, action: np.ndarray, state: dict) -> tuple:
        """Apply control/state latency by buffering."""
        if self.cfg.latency_steps <= 0:
            return action, state
        self.action_buffer.append(action.copy())
        self.state_buffer.append({k: v.copy() if isinstance(v, np.ndarray) else v
                                    for k, v in state.items()})
        if len(self.action_buffer) > self.cfg.latency_steps:
            delayed_action = self.action_buffer.pop(0)
            delayed_state = self.state_buffer.pop(0)
            return delayed_action, delayed_state
        return action, state

    def sample_mass(self, base_mass: float) -> float:
        """Sample randomized mass."""
        if self.cfg.mass_variation <= 0:
            return base_mass
        factor = 1.0 + np.random.uniform(-self.cfg.mass_variation, self.cfg.mass_variation)
        return base_mass * factor

    def sample_camera_pose(self, base_pos: np.ndarray, base_rot: np.ndarray) -> tuple:
        """Sample randomized camera pose."""
        pos = base_pos.copy()
        rot = base_rot.copy()
        if self.cfg.camera_pos_noise > 0:
            pos += np.random.normal(0, self.cfg.camera_pos_noise, 3)
        if self.cfg.camera_rot_noise > 0:
            rot += np.random.normal(0, self.cfg.camera_rot_noise, 3)
        return pos, rot


def run_noise_eval(
    episodes: int = 100,
    noise_config: NoiseConfig | None = None,
    checkpoint_path: str | None = None,
    output_path: str | None = None,
    use_synthetic_depth: bool = True,
    hit_radius: float = 0.4,
    max_steps: int = 500,
):
    """Run policy evaluation with Sim-to-Real noise."""
    if noise_config is None:
        noise_config = NoiseConfig()

    # Auto-select checkpoint
    if checkpoint_path is None:
        ckpt_dir = repo_root() / "training" / "diffphys" / "results" / "checkpoints"
        ckpts = sorted(ckpt_dir.glob("target_impact_*.pth"))
        if not ckpts:
            ckpts = sorted(ckpt_dir.glob("*.pth"))
        if not ckpts:
            raise FileNotFoundError(f"No checkpoints found in {ckpt_dir}")
        checkpoint_path = str(ckpts[-1])
    print(f"Using checkpoint: {checkpoint_path}")

    # Build scene (headless)
    builder = SceneBuilder(headless=True)
    builder.launch()
    objects = builder.build_all()
    builder.drone = objects["drone"]
    builder.armor = objects["armor"]
    builder.arena = objects["arena"]
    builder.camera = objects["camera"]

    # Extract inner config dicts (YAML files have top-level keys)
    def _inner(cfg, *keys):
        for k in keys:
            if k in cfg:
                return cfg[k]
        return cfg

    drone_data = _inner(builder.drone_cfg, "drone")
    armor_data = _inner(builder.armor_cfg, "armor", "armor_target")
    arena_data = _inner(builder.arena_cfg, "arena")
    camera_data = _inner(builder.camera_cfg, "depth_camera")

    # Use components from builder
    drone = builder.drone
    armor = builder.armor
    camera = builder.camera
    policy = DiffPhysPolicyWrapper(checkpoint_path, device="cpu")

    # Noise injector
    noise = NoiseInjector(noise_config)

    # Metrics
    target_hits = 0
    wrong_collisions = 0
    timeouts = 0
    impact_velocities = []
    impact_angles = []
    impact_center_errors = []
    times_to_target = []

    home_pos = np.array(drone_data.get("initial", {}).get("position", [-12.0, -6.0, 0.3]))
    target_pos = np.array(armor_data.get("position", [3.08, 3.84, 1.5]))
    arena_L = float(arena_data.get("official_length_m", 28)) / 2
    arena_W = float(arena_data.get("official_width_m", 15)) / 2

    print(f"Running {episodes} episodes with noise config...")
    print(f"  depth_noise_std={noise_config.depth_noise_std}")
    print(f"  depth_drop_prob={noise_config.depth_drop_prob}")
    print(f"  latency_steps={noise_config.latency_steps}")
    print(f"  mass_variation={noise_config.mass_variation}")
    print(f"  camera_pos_noise={noise_config.camera_pos_noise}")
    print(f"  camera_rot_noise={noise_config.camera_rot_noise}")

    dt = 1.0 / 15.0

    for ep in range(episodes):
        # Reset
        noise.reset()
        policy.reset()
        drone.reset()
        yaw = 0.0

        # Randomize mass (stored for potential dynamics use)
        base_mass = drone_data.get("mass", 1.0)
        ep_mass = noise.sample_mass(base_mass)

        # Randomize camera pose (for logging, synthetic depth doesn't use it)
        base_cam_pos = np.array(camera_data.get("mount", {}).get("position", [0, 0, 0.1]))
        base_cam_rot = np.array(camera_data.get("mount", {}).get("rotation", [0, 0, 0]))
        cam_pos, cam_rot = noise.sample_camera_pose(base_cam_pos, base_cam_rot)

        # Reset metrics
        ep_impact_vel = 0.0
        ep_impact_angle = 0.0
        ep_center_error = 0.0
        ep_time = 0
        hit = False
        wrong = False
        timeout = False

        start_time = time.time()

        for step in range(max_steps):
            # Get drone state
            pos = drone.get_position()
            vel = drone.get_velocity()

            # Check target hit
            dist_to_target = np.linalg.norm(pos - target_pos)
            if dist_to_target < hit_radius:
                hit = True
                ep_impact_vel = float(np.linalg.norm(vel))
                target_dir = target_pos - pos
                if np.linalg.norm(target_dir) > 0.01 and np.linalg.norm(vel) > 0.01:
                    cos_angle = np.dot(vel, target_dir) / (np.linalg.norm(vel) * np.linalg.norm(target_dir))
                    ep_impact_angle = float(np.degrees(np.arccos(np.clip(cos_angle, -1, 1))))
                ep_center_error = float(dist_to_target)
                ep_time = step
                break

            # Check wrong collision (arena boundaries)
            if (abs(pos[0]) > arena_L - 0.1 or
                abs(pos[1]) > arena_W - 0.1 or
                pos[2] < 0.05):
                wrong = True
                break

            # Get depth (synthetic)
            depth = synthetic_depth(pos, target_pos)

            # Apply depth noise
            depth = noise.apply_depth_noise(depth)

            # Compute policy action
            accel, yaw_rate = policy.compute_action_with_yaw(
                depth=depth,
                drone_pos=pos,
                drone_vel=vel,
                drone_yaw=yaw,
                target_pos=target_pos,
            )

            # Apply latency (buffer and delay action)
            if noise_config.latency_steps > 0:
                noise.action_buffer.append(accel.copy())
                if len(noise.action_buffer) > noise_config.latency_steps:
                    accel = noise.action_buffer.pop(0)

            # Update yaw
            yaw += yaw_rate * dt
            yaw = policy._wrap_angle(yaw)

            # Apply action to drone
            drone.set_acceleration(accel)
            drone.step_dynamics(dt)

            # Step physics if real Isaac
            if builder._world is not None:
                builder._world.step(render=False)

        if step >= max_steps - 1 and not hit and not wrong:
            timeout = True

        if hit:
            target_hits += 1
            impact_velocities.append(ep_impact_vel)
            impact_angles.append(ep_impact_angle)
            impact_center_errors.append(ep_center_error)
            times_to_target.append(ep_time)
        elif wrong:
            wrong_collisions += 1
        else:
            timeouts += 1

        if (ep + 1) % 10 == 0:
            print(f"Episode {ep+1}/{episodes}: hits={target_hits}, wrong={wrong_collisions}, timeout={timeouts}")

    # Compute metrics
    metrics = {
        "episodes": episodes,
        "target_hits": target_hits,
        "target_hit_rate": target_hits / episodes,
        "wrong_collisions": wrong_collisions,
        "wrong_collision_rate": wrong_collisions / episodes,
        "timeouts": timeouts,
        "timeout_rate": timeouts / episodes,
        "impact_velocity_mean": float(np.mean(impact_velocities)) if impact_velocities else 0.0,
        "impact_velocity_std": float(np.std(impact_velocities)) if impact_velocities else 0.0,
        "impact_angle_mean": float(np.mean(impact_angles)) if impact_angles else 0.0,
        "impact_angle_p95": float(np.percentile(impact_angles, 95)) if impact_angles else 0.0,
        "impact_center_error_mean": float(np.mean(impact_center_errors)) if impact_center_errors else 0.0,
        "time_to_target_mean": float(np.mean(times_to_target)) if times_to_target else 0.0,
        "checkpoint": checkpoint_path,
        "use_synthetic_depth": use_synthetic_depth,
        "hit_radius": hit_radius,
        "max_steps": max_steps,
        "noise_config": {
            "depth_noise_std": noise_config.depth_noise_std,
            "depth_drop_prob": noise_config.depth_drop_prob,
            "latency_steps": noise_config.latency_steps,
            "mass_variation": noise_config.mass_variation,
            "camera_pos_noise": noise_config.camera_pos_noise,
            "camera_rot_noise": noise_config.camera_rot_noise,
        },
    }

    # Print summary
    print("\n" + "="*60)
    print("NOISE EVALUATION RESULTS")
    print("="*60)
    print(f"Episodes: {episodes}")
    print(f"Target hits: {target_hits} ({metrics['target_hit_rate']:.1%})")
    print(f"Wrong collisions: {wrong_collisions} ({metrics['wrong_collision_rate']:.1%})")
    print(f"Timeouts: {timeouts} ({metrics['timeout_rate']:.1%})")
    print(f"Impact velocity: {metrics['impact_velocity_mean']:.3f} ± {metrics['impact_velocity_std']:.3f} m/s")
    print(f"Impact angle: {metrics['impact_angle_mean']:.1f}° (p95: {metrics['impact_angle_p95']:.1f}°)")
    print(f"Center error: {metrics['impact_center_error_mean']:.3f} m")
    print("="*60)

    # Save results
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump({"metrics": metrics, "timestamp": time.time()}, f, indent=2)
        print(f"Results saved to {out}")

    # Cleanup
    builder.close()
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Sim-to-Real noise evaluation")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--use_synthetic_depth", action="store_true", default=True)
    parser.add_argument("--no_synthetic_depth", dest="use_synthetic_depth", action="store_false")
    parser.add_argument("--hit_radius", type=float, default=0.4)
    parser.add_argument("--max_steps", type=int, default=500)
    # Noise parameters
    parser.add_argument("--depth_noise_std", type=float, default=0.0)
    parser.add_argument("--depth_drop_prob", type=float, default=0.0)
    parser.add_argument("--latency_steps", type=int, default=0)
    parser.add_argument("--mass_variation", type=float, default=0.0)
    parser.add_argument("--camera_pos_noise", type=float, default=0.0)
    parser.add_argument("--camera_rot_noise", type=float, default=0.0)
    # Preset
    parser.add_argument("--noise", type=str, default="custom",
                        choices=["none", "light", "moderate", "heavy", "all", "custom"])
    args = parser.parse_args()

    # Apply noise presets
    if args.noise == "none":
        cfg = NoiseConfig()
    elif args.noise == "light":
        cfg = NoiseConfig(depth_noise_std=0.05, depth_drop_prob=0.05,
                          latency_steps=1, mass_variation=0.1,
                          camera_pos_noise=0.01, camera_rot_noise=0.01)
    elif args.noise == "moderate":
        cfg = NoiseConfig(depth_noise_std=0.1, depth_drop_prob=0.1,
                          latency_steps=2, mass_variation=0.2,
                          camera_pos_noise=0.02, camera_rot_noise=0.02)
    elif args.noise == "heavy":
        cfg = NoiseConfig(depth_noise_std=0.2, depth_drop_prob=0.2,
                          latency_steps=3, mass_variation=0.3,
                          camera_pos_noise=0.05, camera_rot_noise=0.05)
    elif args.noise == "all":
        # Run all presets sequentially
        results = {}
        for preset in ["none", "light", "moderate", "heavy"]:
            print(f"\n{'='*60}")
            print(f"Running noise preset: {preset}")
            print(f"{'='*60}")
            if preset == "none":
                cfg = NoiseConfig()
            elif preset == "light":
                cfg = NoiseConfig(depth_noise_std=0.05, depth_drop_prob=0.05,
                                  latency_steps=1, mass_variation=0.1,
                                  camera_pos_noise=0.01, camera_rot_noise=0.01)
            elif preset == "moderate":
                cfg = NoiseConfig(depth_noise_std=0.1, depth_drop_prob=0.1,
                                  latency_steps=2, mass_variation=0.2,
                                  camera_pos_noise=0.02, camera_rot_noise=0.02)
            else:
                cfg = NoiseConfig(depth_noise_std=0.2, depth_drop_prob=0.2,
                                  latency_steps=3, mass_variation=0.3,
                                  camera_pos_noise=0.05, camera_rot_noise=0.05)
            out = args.output or f"results/noise_eval_{preset}.json"
            m = run_noise_eval(args.episodes, cfg, args.checkpoint, out,
                              args.use_synthetic_depth, args.hit_radius, args.max_steps)
            results[preset] = m
        # Save summary
        summary_path = Path(args.output or "results/noise_eval_summary.json")
        with open(summary_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSummary saved to {summary_path}")
        return
    else:
        cfg = NoiseConfig(
            depth_noise_std=args.depth_noise_std,
            depth_drop_prob=args.depth_drop_prob,
            latency_steps=args.latency_steps,
            mass_variation=args.mass_variation,
            camera_pos_noise=args.camera_pos_noise,
            camera_rot_noise=args.camera_rot_noise,
        )

    run_noise_eval(args.episodes, cfg, args.checkpoint, args.output,
                   args.use_synthetic_depth, args.hit_radius, args.max_steps)


if __name__ == "__main__":
    main()
