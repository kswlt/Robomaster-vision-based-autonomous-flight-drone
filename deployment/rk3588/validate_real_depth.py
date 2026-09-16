#!/usr/bin/env python3
"""Real-depth algorithm validation on Orange Pi 5.

Reads RealSense D430 depth, runs Policy inference, records statistics.
No flight control, no arming - pure algorithm verification.
"""
import sys
import time
import numpy as np
from pathlib import Path

# Add repo to path
sys.path.insert(0, str(Path(__file__).parent / "repo"))
from deployment.rk3588.inference import RK3588Policy

# --- RealSense ---
import pyrealsense2 as rs

def init_camera(width=640, height=480, fps=30):
    for w, h, f in [(width, height, fps), (640, 480, 30), (480, 270, 60), (256, 144, 90)]:
        try:
            config = rs.config()
            config.enable_stream(rs.stream.depth, w, h, rs.format.z16, f)
            pipeline = rs.pipeline()
            pipeline.start(config)
            print(f"[Camera] RealSense started: {w}x{h}@{f}fps")
            return pipeline, (w, h, f)
        except Exception as e:
            print(f"[Camera] {w}x{h}@{f} failed: {e}")
    raise RuntimeError("Cannot start RealSense")


def main():
    N_FRAMES = 600  # 20 seconds at 30fps
    WARMUP = 30

    print("=" * 60)
    print("E2E-RL Real-Depth Algorithm Validation")
    print("=" * 60)

    # Init camera
    pipeline, (w, h, fps) = init_camera()

    # Init policy
    model_path = str(Path(__file__).parent / "repo" / "deployment" / "onnx" / "policy.onnx")
    policy = RK3588Policy(model_path, use_npu=False)
    print(f"[Policy] Loaded from {model_path}")

    # Simulated drone state (since we're on the ground)
    # In real flight these come from FC
    drone_pos = np.array([0.0, 0.0, 1.0])   # 1m altitude
    drone_vel = np.array([0.0, 0.0, 0.0])
    drone_yaw = 0.0
    target_pos = np.array([3.0, 0.0, 1.0])   # target 3m ahead

    # Statistics
    depths_min = []
    depths_max = []
    depths_mean = []
    depths_valid_ratio = []
    actions = []
    latencies = []
    state_norms = []

    print(f"\nRunning {N_FRAMES} frames of validation...")
    print(f"Drone: pos={drone_pos}, target={target_pos}")
    print(f"{'Frame':>6} {'depth_min':>9} {'depth_max':>9} {'depth_mean':>10} {'valid%':>6} {'ax':>7} {'ay':>7} {'az':>7} {'lat_ms':>7}")
    print("-" * 80)

    for i in range(N_FRAMES):
        t0 = time.time()

        # Get depth
        frames = pipeline.wait_for_frames(5000)
        depth_frame = frames.get_depth_frame()
        if not depth_frame:
            continue
        depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0  # mm -> m

        # Depth stats
        valid = depth > 0
        valid_ratio = valid.sum() / depth.size
        if valid_ratio > 0:
            d_min = depth[valid].min()
            d_max = depth[valid].max()
            d_mean = depth[valid].mean()
        else:
            d_min = d_max = d_mean = 0.0

        # Run policy
        result = policy.infer(depth, drone_pos, drone_vel, drone_yaw, target_pos)
        accel = result["accel"]
        latency = result["latency_ms"]

        # Record
        if i >= WARMUP:
            depths_min.append(d_min)
            depths_max.append(d_max)
            depths_mean.append(d_mean)
            depths_valid_ratio.append(valid_ratio)
            actions.append(accel)
            latencies.append(latency)

        # Print every 30 frames
        if i % 30 == 0:
            print(f"{i:6d} {d_min:9.3f} {d_max:9.3f} {d_mean:10.3f} "
                  f"{valid_ratio*100:5.1f}% {accel[0]:7.3f} {accel[1]:7.3f} "
                  f"{accel[2]:7.3f} {latency:7.2f}")

    pipeline.stop()

    # Summary
    actions = np.array(actions)
    latencies = np.array(latencies)

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Frames analyzed: {len(actions)}")
    print(f"\n--- Depth Camera ---")
    print(f"  Resolution: {w}x{h}@{fps}fps")
    print(f"  Valid pixel ratio: {np.mean(depths_valid_ratio)*100:.1f}% "
          f"(min={np.min(depths_valid_ratio)*100:.1f}%, max={np.max(depths_valid_ratio)*100:.1f}%)")
    print(f"  Depth range: {np.mean(depths_min):.3f} - {np.mean(depths_max):.3f} m")
    print(f"  Mean depth: {np.mean(depths_mean):.3f} m")
    print(f"\n--- Policy Inference ---")
    print(f"  Latency: mean={np.mean(latencies):.2f}ms, p50={np.percentile(latencies,50):.2f}ms, "
          f"p95={np.percentile(latencies,95):.2f}ms, p99={np.percentile(latencies,99):.2f}ms")
    print(f"\n--- Action Output (accel, m/s^2) ---")
    print(f"  ax: mean={actions[:,0].mean():.3f}, std={actions[:,0].std():.3f}, "
          f"range=[{actions[:,0].min():.3f}, {actions[:,0].max():.3f}]")
    print(f"  ay: mean={actions[:,1].mean():.3f}, std={actions[:,1].std():.3f}, "
          f"range=[{actions[:,1].min():.3f}, {actions[:,1].max():.3f}]")
    print(f"  az: mean={actions[:,2].mean():.3f}, std={actions[:,2].std():.3f}, "
          f"range=[{actions[:,2].min():.3f}, {actions[:,2].max():.3f}]")
    print(f"  |accel|: mean={np.linalg.norm(actions, axis=1).mean():.3f} m/s^2")

    # Sanity checks
    print(f"\n--- Sanity Checks ---")
    checks = []
    # 1. Depth valid ratio > 10%
    check1 = np.mean(depths_valid_ratio) > 0.10
    checks.append(("Depth valid ratio > 10%", check1, f"{np.mean(depths_valid_ratio)*100:.1f}%"))
    # 2. Policy latency < 50ms
    check2 = np.percentile(latencies, 95) < 50
    checks.append(("Policy p95 latency < 50ms", check2, f"{np.percentile(latencies,95):.2f}ms"))
    # 3. Action finite
    check3 = np.all(np.isfinite(actions))
    checks.append(("All actions finite", check3, f"max={np.abs(actions).max():.3f}"))
    # 4. Action range reasonable (< 20 m/s^2)
    check4 = np.abs(actions).max() < 20
    checks.append(("|accel| < 20 m/s^2", check4, f"max={np.abs(actions).max():.3f}"))

    all_pass = True
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {name}: {detail}")

    print(f"\n{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    print("=" * 60)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
