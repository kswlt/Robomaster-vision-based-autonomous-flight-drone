# Project Handoff

## Last Updated

2026-09-05

## Current Goal

Validate D435 stereo IR acquisition and timing as the Pure Stereo VO baseline input.

## Current Phase

Phase A — D435 stereo IR acquisition and timing validation.

## Current Status

IN_PROGRESS (Phase A); Phase 0 remains PASS.

## What Was Just Done

Completed a read-only librealsense package-source assessment for Phase A.

## Verified Facts

- NX: `nvidia-sentry`, Ubuntu 22.04.5, kernel `5.15.148-tegra`, L4T 36.4.3, CUDA 12.6.
- Direct Ethernet: Windows `10.42.0.70/24` to NX `10.42.0.2/24`; 1 ms ping and SSH pass.
- ROS 2 Humble is installed but was not sourced in the audit shell.
- Attached RealSense is the intended D435, PID `8086:0b07`, serial `943623021659`, at USB 3 / 5 Gbps.
- Six V4L2 video nodes exist. No HID/IIO IMU is expected because D435 has no internal IMU. Root disk has 17 GiB free (86% used).
- The `nvidia` user has verified read/write access to the D435 video nodes.
- Current apt sources have ROS RealSense wrapper packages, but no `librealsense2-*` runtime, development, or viewer package.

## Inferred Facts

- L4T 36.4.3 is the JetPack 6.2 baseline.

## Unknown Facts

- RMW when ROS is sourced; D435 stereo acquisition/timing performance; PX4 IMU availability.

## Development Host

Windows source of truth and WSL Ubuntu 22.04.4; GitHub SSH works.

## Jetson NX Environment

See `docs/phases/phase0_nx_environment_audit.md`.

## D435 State

VERIFIED: D435 is connected at USB 3 / 5 Gbps. Stereo stream acquisition remains unverified.

## VIO State

Pure Stereo VO not deployed. PX4 stereo-inertial VIO is a later stage.

## Depth State

Not tested; depth is off during the Stereo VO baseline.

## Runtime Architecture

D435 left/right IR → Pure Stereo VO → PX4-IMU Stereo-Inertial VIO → A/B benchmark → impact-aware recovery supervisor.

## Important Paths

- Repository: `C:\Users\Admin\Desktop\无人机\Robomaster-vision-based-autonomous-flight-drone`
- NX direct SSH: `nvidia@10.42.0.2`

## Important Commands

- `ssh -i %USERPROFILE%\\.ssh\\robomaster_nx_audit nvidia@10.42.0.2`
- `git pull --ff-only origin main`

## Running Processes / Services

No project runtime started.

## Current Performance

Baseline CPU 0–5%, GPU 0%, RAM 1.86/7.62 GB, input power about 4.4 W.

## Known Problems

Stereo acquisition/timing is not yet benchmarked. librealsense is absent; no supported binary package is currently configured.

## Failed Attempts

The old address `10.33.154.71` is stale; do not reuse it.

No failed experiment in the revised route. The former camera-model mismatch was a documentation error corrected by this checkpoint.

## Do Not Repeat

- Do not search for a D435 internal IMU; VIO will use PX4 IMU later.
- Do not enable RGB, depth, or point clouds in the first stereo acquisition test.
- Do not install a DKMS package, modify BSP/L4T, or install packages before a minimal-risk dependency plan is approved.
- Do not commit credentials or private keys.

## Risks

Root disk is 86% full; avoid large downloads, builds, datasets, and rosbags. librealsense is absent.

## Next Recommended Step

Approve a minimal-risk user-space librealsense source build (no DKMS, kernel, or BSP changes), then validate D435 left/right IR at 640×480@30 for 60 seconds with RGB/depth/point cloud off.

## Exact Next Commands

After approval, fetch a pinned librealsense release and build only user-space tools/libraries in a temporary build directory.

## Files Changed

Phase 0 report and state documentation.

## Latest Test Results

Phase 0: PASS. Phase A D435 acquisition: NOT STARTED.

## Rollback Information

To restore host Ethernet, set `以太网 4` to `192.168.0.200/24` with no gateway. Git changes are documentation only.
