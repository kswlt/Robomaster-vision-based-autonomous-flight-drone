"""Interactive GUI demo with manual drone control in Isaac Sim.

Controls (click the Isaac Sim viewport first to focus):
  W/A/S/D    - Move drone horizontally (forward/left/back/right)
  Q/E        - Move down/up
  Arrow keys - Rotate yaw
  Space      - Toggle AI policy control / manual control
  R          - Reset drone to HOME position
  T          - Teleport drone near armor target
  P          - Pause / resume simulation
  H          - Print help
  Close window to exit

Usage:
    C:\\isaacsim\\python.bat -m sim.isaac.demo_interactive
    C:\\isaacsim\\python.bat -m sim.isaac.demo_interactive --manual  # start in manual mode
    C:\\isaacsim\\python.bat -m sim.isaac.demo_interactive --speed 8.0  # faster manual flight
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sim.common.config import repo_root
from sim.isaac.build_scene import SceneBuilder
from sim.isaac.policy_wrapper import DiffPhysPolicyWrapper


# Virtual key codes for Windows GetAsyncKeyState
VK_CODES = {
    'W': 0x57, 'A': 0x41, 'S': 0x53, 'D': 0x44,
    'Q': 0x51, 'E': 0x45, 'R': 0x52, 'P': 0x50,
    'T': 0x54, 'H': 0x48, 'SPACE': 0x20, 'ESC': 0x1B,
    'UP': 0x26, 'DOWN': 0x28, 'LEFT': 0x25, 'RIGHT': 0x27,
}


def poll_keys():
    """Poll current keyboard state via Windows API."""
    user32 = ctypes.windll.user32
    pressed = set()
    for name, vk in VK_CODES.items():
        if user32.GetAsyncKeyState(vk) & 0x8000:
            pressed.add(name)
    return pressed


def synthetic_depth(drone_pos, target_pos, height=48, width=64):
    """Generate synthetic depth image for policy input."""
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


def print_help():
    print("\n" + "=" * 55)
    print("CONTROLS (click viewport first to focus):")
    print("  W/A/S/D    - Move horizontally")
    print("  Q/E        - Down / Up")
    print("  Arrow L/R  - Rotate yaw")
    print("  Space      - Toggle AI / Manual")
    print("  R          - Reset to HOME")
    print("  T          - Teleport to target")
    print("  P          - Pause / Resume")
    print("  H          - Show this help")
    print("  Close window to exit")
    print("=" * 55 + "\n")


def run_interactive(start_manual=False, move_speed=6.0):
    """Run interactive Isaac Sim session."""
    print("=" * 60)
    print("E2E-RL Interactive Drone Control - Isaac Sim GUI")
    print("=" * 60)
    print_help()
    print("Launching Isaac Sim GUI... (~30 seconds)")

    # Build scene
    builder = SceneBuilder(headless=False)
    builder.launch()
    objects = builder.build_all()
    drone = objects["drone"]
    armor = objects["armor"]
    world = builder._world

    # Config values
    home_pos = drone.init_pos.copy()
    target_pos = armor.position.copy()

    # Load policy
    ckpt_dir = repo_root() / "training" / "diffphys" / "results" / "checkpoints"
    ckpts = sorted(ckpt_dir.glob("target_impact_*.pth"))
    policy = None
    if ckpts:
        policy = DiffPhysPolicyWrapper(str(ckpts[-1]), device="cpu")
        print(f"Loaded policy: {ckpts[-1].name}")
    else:
        print("WARNING: No policy checkpoint found, manual only")

    # State
    use_ai = not start_manual
    paused = False
    total_hits = 0
    step = 0
    yaw = 0.0
    dt = 1.0 / 15.0

    print(f"\nHOME:   {home_pos}")
    print(f"TARGET: {target_pos}")
    print(f"Mode:   {'AI Policy' if use_ai else 'Manual'}")
    print(f"\n{'='*60}")
    print("READY - Fly the drone! Press H for controls.")
    print("=" * 60)

    drone.reset()
    prev_keys = set()
    last_status = 0
    startup_frames = 90  # ignore keyboard input for first ~6 seconds

    try:
        while True:
            keys = poll_keys()

            # During startup, just render and ignore input
            if startup_frames > 0:
                startup_frames -= 1
                if startup_frames == 0:
                    print("\n>>> Input active! Click the viewport and use WASD to fly.")
                world.step(render=True)
                continue

            newly_pressed = keys - prev_keys
            prev_keys = keys.copy()

            # Edge-triggered commands (no Esc - close window to exit)

            if 'H' in newly_pressed:
                print_help()

            if 'SPACE' in newly_pressed:
                use_ai = not use_ai
                print(f"\n>>> Mode: {'AI POLICY' if use_ai else 'MANUAL'}")

            if 'P' in newly_pressed:
                paused = not paused
                print(f"\n>>> {'PAUSED' if paused else 'RESUMED'}")

            if 'R' in newly_pressed:
                drone.reset()
                yaw = 0.0
                if policy:
                    policy.reset()
                step = 0
                print("\n>>> Reset to HOME")

            if 'T' in newly_pressed:
                # Teleport near target
                tp_pos = target_pos + np.array([-1.0, 0.0, 0.5])
                drone._position = tp_pos.copy()
                drone._velocity = np.zeros(3)
                drone._yaw = 0.0
                yaw = 0.0
                if drone._prim:
                    drone._prim.set_world_pose(position=tp_pos)
                    drone._prim.set_linear_velocity(np.zeros(3))
                print(f"\n>>> Teleported to {tp_pos}")

            if paused:
                world.step(render=True)
                continue

            # Get state
            pos = drone.get_position()
            vel = drone.get_velocity()

            # Check hit
            dist_to_target = armor.center_distance(pos)
            if dist_to_target < 0.4:
                total_hits += 1
                impact_speed = float(np.linalg.norm(vel))
                impact_angle = armor.impact_angle_deg(vel)
                print(f"\n  *** TARGET HIT! (total hits: {total_hits}) ***")
                print(f"      Impact speed: {impact_speed:.3f} m/s")
                print(f"      Impact angle: {impact_angle:.1f} deg")
                print(f"      Position: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")
                armor.mark_hit()
                time.sleep(1.0)
                drone.reset()
                yaw = 0.0
                if policy:
                    policy.reset()
                step = 0
                world.step(render=True)
                continue

            # Compute action
            if use_ai and policy is not None:
                # AI policy
                depth = synthetic_depth(pos, target_pos)
                action = policy.compute_action_with_yaw(depth, pos, vel, yaw, target_pos)
                accel = np.asarray(action[0], dtype=np.float64)
                drone.set_acceleration(accel)
                drone.step_dynamics(dt)
                if action[1] is not None:
                    yaw += float(action[1]) * dt
                    drone._yaw = yaw
            else:
                # Manual control - velocity command
                forward = np.array([np.cos(yaw), np.sin(yaw), 0.0])
                right = np.array([-np.sin(yaw), np.cos(yaw), 0.0])

                target_vel = np.zeros(3)
                if 'W' in keys:
                    target_vel += forward * move_speed
                if 'S' in keys:
                    target_vel -= forward * move_speed
                if 'D' in keys:
                    target_vel += right * move_speed
                if 'A' in keys:
                    target_vel -= right * move_speed
                if 'E' in keys:
                    target_vel[2] += move_speed
                if 'Q' in keys:
                    target_vel[2] -= move_speed

                # Yaw
                if 'LEFT' in keys:
                    yaw += 2.0 * dt
                if 'RIGHT' in keys:
                    yaw -= 2.0 * dt

                # Smooth velocity and apply
                new_vel = vel + (target_vel - vel) * min(1.0, dt * 8.0)
                drone._velocity = new_vel
                drone._position = pos + new_vel * dt
                drone._yaw = yaw
                if drone._prim:
                    drone._prim.set_world_pose(position=drone._position)
                    drone._prim.set_linear_velocity(new_vel)

            # Step physics
            world.step(render=True)
            step += 1

            # Status every 30 steps
            if step - last_status >= 30:
                last_status = step
                dist = np.linalg.norm(target_pos - pos)
                speed = np.linalg.norm(vel)
                mode = "AI" if use_ai else "MAN"
                print(f"  [{mode}] step={step:4d} "
                      f"pos=[{pos[0]:6.2f},{pos[1]:6.2f},{pos[2]:5.2f}] "
                      f"dist={dist:5.2f}m vel={speed:5.2f}m/s "
                      f"yaw={np.degrees(yaw):6.1f}deg")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n{'='*60}")
        print(f"Session ended. Total hits: {total_hits}")
        print(f"{'='*60}")
        builder.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Interactive drone control in Isaac Sim")
    parser.add_argument("--manual", action="store_true", help="Start in manual control mode")
    parser.add_argument("--speed", type=float, default=6.0, help="Manual movement speed (m/s)")
    args = parser.parse_args()
    run_interactive(start_manual=args.manual, move_speed=args.speed)
