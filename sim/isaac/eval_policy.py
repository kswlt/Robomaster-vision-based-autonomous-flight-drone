"""Policy-based evaluation in Isaac Sim (milestone 4).

Loads a trained DiffPhys checkpoint and runs N episodes in Isaac Sim.
Uses depth camera (or synthetic depth fallback) + ground truth state.

Usage:
    python -m sim.isaac.eval_policy --checkpoint path/to/ckpt.pth --episodes 1000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from sim.common.config import load_config, repo_root
from sim.isaac.build_scene import SceneBuilder
from sim.isaac.policy_wrapper import DiffPhysPolicyWrapper


def load_all_configs() -> dict:
    """Load and merge all relevant configs."""
    cfg = {}
    for name in ["arena", "armor", "drone", "depth_camera", "evaluation", "training"]:
        try:
            cfg.update(load_config(name))
        except FileNotFoundError:
            pass
    return cfg


def parse_args():
    p = argparse.ArgumentParser(description="DiffPhys policy evaluation in Isaac Sim")
    p.add_argument("--checkpoint", default=None, help="Path to DiffPhys checkpoint .pth")
    p.add_argument("--episodes", type=int, default=100)
    p.add_argument("--max_steps", type=int, default=500)
    p.add_argument("--hit_radius", type=float, default=0.4)
    p.add_argument("--dt", type=float, default=1.0 / 15.0)
    p.add_argument("--device", default="cpu", help="cpu or cuda")
    p.add_argument("--use_synthetic_depth", action="store_true", default=True,
                   help="Use synthetic depth instead of Isaac camera (faster, for validation)")
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--output", default="results/policy_eval.json")
    return p.parse_args()


def synthetic_depth(drone_pos: np.ndarray, target_pos: np.ndarray,
                    arena_size: tuple = (28, 15), height: int = 48, width: int = 64) -> np.ndarray:
    """Generate synthetic depth image from drone position.

    Simple model: depth = distance to nearest surface in each ray direction.
    For validation purposes, we use a simplified depth that encodes the target.
    """
    depth = np.full((height, width), 24.0, dtype=np.float32)

    # Target direction
    target_dir = target_pos - drone_pos
    target_dist = np.linalg.norm(target_dir)
    if target_dist > 0.1:
        target_dir = target_dir / target_dist
        # Project target into center of depth image
        cy, cx = height // 2, width // 2
        # Simple: set a small region around center to target distance
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                y, x = cy + dy, cx + dx
                if 0 <= y < height and 0 <= x < width:
                    depth[y, x] = target_dist

    # Floor depth (drone height)
    floor_depth = drone_pos[2]
    if floor_depth > 0.3:
        depth[height // 2:, :] = np.minimum(depth[height // 2:, :], floor_depth)

    return depth


def run_episode(builder, policy, args, episode_id: int) -> dict:
    """Run one episode with the policy."""
    cfg = builder.cfg
    drone = builder.drone
    armor = builder.armor
    arena_cfg = cfg["arena"]

    # Reset
    drone.reset()
    policy.reset()

    home_pos = np.array(cfg["drone"]["initial"]["position"], dtype=float)
    target_pos = np.array(cfg["armor"]["position"], dtype=float)

    hit = False
    wrong_collision = False
    timeout = False
    impact_velocity = 0.0
    impact_angle = 0.0
    impact_center_error = 0.0
    steps = 0
    yaw = 0.0

    start_time = time.time()

    for step in range(args.max_steps):
        steps = step + 1
        pos = drone.get_position()
        vel = drone.get_velocity()

        # Check target hit
        dist_to_target = np.linalg.norm(pos - target_pos)
        if dist_to_target < args.hit_radius:
            hit = True
            impact_velocity = float(np.linalg.norm(vel))
            # Impact angle: angle between velocity and target direction
            target_dir = target_pos - pos
            if np.linalg.norm(target_dir) > 0.01 and np.linalg.norm(vel) > 0.01:
                cos_angle = np.dot(vel, target_dir) / (np.linalg.norm(vel) * np.linalg.norm(target_dir))
                impact_angle = float(np.degrees(np.arccos(np.clip(cos_angle, -1, 1))))
            impact_center_error = float(dist_to_target)
            break

        # Check wrong collision (hit arena walls/floor)
        arena_L = float(arena_cfg["official_length_m"]) / 2
        arena_W = float(arena_cfg["official_width_m"]) / 2
        if (abs(pos[0]) > arena_L - 0.1 or abs(pos[1]) > arena_W - 0.1 or pos[2] < 0.05):
            wrong_collision = True
            break

        # Get depth
        if args.use_synthetic_depth:
            depth = synthetic_depth(pos, target_pos)
        else:
            depth = builder.camera.get_depth() if builder.camera else synthetic_depth(pos, target_pos)

        # Compute policy action
        accel, yaw_rate = policy.compute_action_with_yaw(
            depth=depth,
            drone_pos=pos,
            drone_vel=vel,
            drone_yaw=yaw,
            target_pos=target_pos,
        )

        # Update yaw
        yaw += yaw_rate * args.dt
        yaw = policy._wrap_angle(yaw)

        # Apply action to drone (acceleration-based kinematic model)
        drone.set_acceleration(accel)
        drone.step_dynamics(args.dt)

        # Step physics if using real Isaac
        if builder._world is not None:
            builder._world.step(render=False)

    if steps >= args.max_steps and not hit and not wrong_collision:
        timeout = True

    time_to_target = time.time() - start_time

    return {
        "episode_id": episode_id,
        "hit": hit,
        "wrong_collision": wrong_collision,
        "timeout": timeout,
        "impact_velocity": impact_velocity,
        "impact_angle": impact_angle,
        "impact_center_error": impact_center_error,
        "time_to_target": time_to_target,
        "steps": steps,
        "final_pos": pos.tolist(),
    }


def main():
    args = parse_args()

    # Default checkpoint
    if args.checkpoint is None:
        ckpt_dir = repo_root() / "training" / "diffphys" / "results" / "checkpoints"
        candidates = sorted(ckpt_dir.glob("target_impact_*.pth"))
        if candidates:
            args.checkpoint = str(candidates[-1])
            print(f"Using latest checkpoint: {args.checkpoint}")
        else:
            print("ERROR: No checkpoint found. Specify --checkpoint")
            return 1

    # Load config
    cfg = load_all_configs()

    # Build Isaac scene
    builder = SceneBuilder(headless=args.headless)
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

    builder.cfg = {
        "arena": _inner(builder.arena_cfg, "arena"),
        "armor": _inner(builder.armor_cfg, "armor", "armor_target"),
        "drone": _inner(builder.drone_cfg, "drone"),
        "camera": _inner(builder.camera_cfg, "depth_camera"),
    }

    # Load policy
    print(f"Loading policy from {args.checkpoint}")
    policy = DiffPhysPolicyWrapper(
        checkpoint_path=args.checkpoint,
        device=args.device,
        max_speed=4.0,
        margin=0.2,
        dt=args.dt,
    )

    # Run episodes
    results = []
    hits = 0
    wrong = 0
    timeouts = 0
    impact_velocities = []
    impact_angles = []
    center_errors = []
    times = []

    print(f"Running {args.episodes} episodes...")
    for ep in range(args.episodes):
        result = run_episode(builder, policy, args, ep)
        results.append(result)

        if result["hit"]:
            hits += 1
            impact_velocities.append(result["impact_velocity"])
            impact_angles.append(result["impact_angle"])
            center_errors.append(result["impact_center_error"])
            times.append(result["time_to_target"])
        if result["wrong_collision"]:
            wrong += 1
        if result["timeout"]:
            timeouts += 1

        if (ep + 1) % 10 == 0:
            print(f"  Episode {ep+1}/{args.episodes}: hits={hits}, wrong={wrong}, timeout={timeouts}")

    # Compute metrics
    metrics = {
        "episodes": args.episodes,
        "target_hits": hits,
        "target_hit_rate": hits / args.episodes,
        "wrong_collisions": wrong,
        "wrong_collision_rate": wrong / args.episodes,
        "timeouts": timeouts,
        "timeout_rate": timeouts / args.episodes,
        "impact_velocity_mean": float(np.mean(impact_velocities)) if impact_velocities else 0.0,
        "impact_velocity_std": float(np.std(impact_velocities)) if impact_velocities else 0.0,
        "impact_angle_mean": float(np.mean(impact_angles)) if impact_angles else 0.0,
        "impact_angle_p95": float(np.percentile(impact_angles, 95)) if impact_angles else 0.0,
        "impact_center_error_mean": float(np.mean(center_errors)) if center_errors else 0.0,
        "time_to_target_mean": float(np.mean(times)) if times else 0.0,
        "checkpoint": args.checkpoint,
        "use_synthetic_depth": args.use_synthetic_depth,
        "hit_radius": args.hit_radius,
        "max_steps": args.max_steps,
    }

    # Save results
    output_path = repo_root() / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({"metrics": metrics, "episodes": results}, f, indent=2)

    print(f"\n=== Results ===")
    print(json.dumps(metrics, indent=2))
    print(f"\nSaved to {output_path}")

    # Cleanup
    builder.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
