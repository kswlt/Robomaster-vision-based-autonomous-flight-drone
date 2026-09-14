"""Real-time GUI visualization of drone impact mission in Isaac Sim.

Launches Isaac Sim with full GUI, shows the RM arena, drone, armor target,
and runs the trained policy in real-time. Watch the drone fly from HOME
to the armor plate and impact it.

Usage:
    C:\\isaacsim\\python.bat -m sim.isaac.demo_gui
    C:\\isaacsim\\python.bat -m sim.isaac.demo_gui --episodes 3
    C:\\isaacsim\\python.bat -m sim.isaac.demo_gui --speed 0.5  # slow motion
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

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


def run_demo(episodes=1, speed=1.0, use_policy=True):
    """Run GUI demo of drone impact mission."""
    print("="*60)
    print("E2E-RL Drone Impact Demo - Isaac Sim GUI")
    print("="*60)
    print(f"\nLaunching Isaac Sim GUI... (this takes ~30 seconds)")
    print("Watch the window for the drone flying to the armor target!")

    # Build scene with GUI (headless=False)
    builder = SceneBuilder(headless=False)
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

    cfg = builder.cfg
    drone = builder.drone
    home_pos = np.array(cfg["drone"]["initial"]["position"], dtype=float)
    target_pos = np.array(cfg["armor"]["position"], dtype=float)
    arena_L = float(cfg["arena"]["official_length_m"]) / 2
    arena_W = float(cfg["arena"]["official_width_m"]) / 2

    # Load policy
    if use_policy:
        ckpt_dir = repo_root() / "training" / "diffphys" / "results" / "checkpoints"
        ckpts = sorted(ckpt_dir.glob("target_impact_*.pth"))
        checkpoint_path = str(ckpts[-1]) if ckpts else None
        print(f"\nLoaded policy: {checkpoint_path}")
        policy = DiffPhysPolicyWrapper(checkpoint_path, device="cpu")
    else:
        policy = None
        print("\nUsing scripted PD controller")

    dt = 1.0 / 15.0
    hit_radius = 0.4
    max_steps = 500

    # Try to set camera view for better visibility
    try:
        from isaacsim.core.api.camera import Camera
        # Set perspective camera to overview the arena
        from pxr import UsdGeom, Gf
        stage = builder._world.stage
        # Find or create perspective camera
        cam_path = "/OmniverseKit_Persp"
        if stage.GetPrimAtPath(cam_path):
            cam = UsdGeom.Camera(stage.GetPrimAtPath(cam_path))
            # Position camera to overview the arena
            cam.GetTranslateAttr().Set(Gf.Vec3d(-5, -12, 10))
            # Look at center of arena
            # This is approximate; user can adjust with mouse
    except Exception as e:
        print(f"Camera setup note: {e}")

    print(f"\nHOME: {home_pos}")
    print(f"TARGET: {target_pos}")
    print(f"Arena: {arena_L*2}m x {arena_W*2}m")
    print(f"Speed multiplier: {speed}x")
    print("\n" + "="*60)
    print("DEMO STARTING - Watch the Isaac Sim window!")
    print("="*60)

    for ep in range(episodes):
        print(f"\n--- Episode {ep+1}/{episodes} ---")
        drone.reset()
        if policy:
            policy.reset()
        yaw = 0.0

        hit = False
        wrong = False
        trajectory = []

        for step in range(max_steps):
            pos = drone.get_position()
            vel = drone.get_velocity()
            trajectory.append(pos.copy())

            # Check hit
            dist = np.linalg.norm(pos - target_pos)
            if dist < hit_radius:
                hit = True
                impact_vel = float(np.linalg.norm(vel))
                print(f"  ✅ TARGET HIT at step {step}!")
                print(f"     Impact velocity: {impact_vel:.3f} m/s")
                print(f"     Position: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")
                break

            # Check wrong collision
            if (abs(pos[0]) > arena_L - 0.1 or abs(pos[1]) > arena_W - 0.1 or pos[2] < 0.05):
                wrong = True
                print(f"  ❌ WRONG COLLISION at step {step}")
                print(f"     Position: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")
                break

            # Get depth
            depth = synthetic_depth(pos, target_pos)

            if policy:
                # Policy control
                accel, yaw_rate = policy.compute_action_with_yaw(
                    depth=depth, drone_pos=pos, drone_vel=vel,
                    drone_yaw=yaw, target_pos=target_pos
                )
                yaw += yaw_rate * dt
                yaw = policy._wrap_angle(yaw)
            else:
                # Simple scripted controller (P control)
                rel = target_pos - pos
                accel = rel * 2.0 - vel * 1.5
                accel[2] += 9.81  # gravity compensation
                yaw = np.arctan2(rel[1], rel[0])

            # Apply action
            drone.set_acceleration(accel)
            drone.step_dynamics(dt)

            # Step physics and render
            if builder._world is not None:
                builder._world.step(render=True)

            # Speed control (slow motion)
            if speed < 1.0:
                time.sleep(dt * (1.0/speed - 1.0))

            # Progress update
            if step % 50 == 0:
                print(f"  Step {step}: pos=[{pos[0]:.1f},{pos[1]:.1f},{pos[2]:.1f}], "
                      f"dist={dist:.2f}m, vel={np.linalg.norm(vel):.2f}m/s")

        if not hit and not wrong:
            print(f"  ⏱️  TIMEOUT after {max_steps} steps")

        # Brief pause between episodes
        if ep < episodes - 1:
            print("  Resetting for next episode...")
            time.sleep(2.0)

    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)
    print(f"\nTotal episodes: {episodes}")
    print(f"Final position: {trajectory[-1] if trajectory else 'N/A'}")
    print("\nThe Isaac Sim window will stay open.")
    print("Close it or press Ctrl+C to exit.")
    print("\nYou can:")
    print("  - Drag with mouse to rotate view")
    print("  - Scroll to zoom")
    print("  - Right-click drag to pan")

    # Keep the app running for user to inspect
    try:
        while True:
            if builder._world is not None:
                builder._world.step(render=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nExiting...")

    builder.close()


def main():
    parser = argparse.ArgumentParser(description="E2E-RL Drone Impact GUI Demo")
    parser.add_argument("--episodes", type=int, default=1, help="Number of episodes to show")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier (0.5 = slow motion)")
    parser.add_argument("--scripted", action="store_true", help="Use scripted controller instead of learned policy")
    args = parser.parse_args()

    run_demo(episodes=args.episodes, speed=args.speed, use_policy=not args.scripted)


if __name__ == "__main__":
    main()
