# Project Handoff

> **2026-09-06 hardware transition notice**: The historical D435/Pure Stereo VO sections below are retained for traceability only. The active hardware is now an Orbbec Astra Pro and the source of truth is `docs/CURRENT_STATE.md` plus `docs/PROJECT_PROMPT_ZH.md`.

## Active Hardware and Connection

- NX hostname: `nvidia-sentry`; Wi-Fi address: `192.168.1.53/23` on `ADAM_5G`.
- Windows SSH command: `ssh -i C:\Users\Admin\.ssh\robomaster_nx_audit nvidia@192.168.1.53`.
- The former direct Ethernet address `10.42.0.2` is currently unavailable because `enP8p1s0` is down.
- PX4 CUAV X7Pro is `/dev/ttyACM0`; use `/dev/serial/by-id/usb-CUAV_PX4_CUAV_X7Pro_0-if00` in new code.
- The attached camera is identified by USB as Orbbec Astra Pro (`2bc5:0502`, `2bc5:0403`) with `/dev/video0` and `/dev/video1`.

## Current Blocker and Required Order

No verified Astra Pro depth stream is available yet. Do not reuse the D435 librealsense pipeline, D435 calibration, or D435-specific ORB-SLAM3 launch files. First install and verify an Astra-compatible Orbbec SDK/ROS 2 driver, enumerate RGB/depth profiles, obtain intrinsics/extrinsics/depth scale, and publish the streams to ROS 2/Foxglove. Only after that should RGB-D VO/VIO be connected to PX4. `vio-watchdog.service` currently restarts legacy processes, so stop or reconfigure that service before launching another process that opens `/dev/ttyACM0`.

## Last Updated

2026-09-06

## Current Goal

Bring up the Orbbec Astra Pro RGB-D input and rebuild the visual-odometry path before any flight test.

## Current Phase

Hardware transition — Astra Pro RGB-D bring-up.

## Current Status

IN_PROGRESS (Phase B); Phase A and Phase 0 are PASS.

## What Was Just Done

Completed the resource-enhanced 60-second D435 stereo IR timing benchmark.

## Verified Facts

- NX: `nvidia-sentry`, Ubuntu 22.04.5, kernel `5.15.148-tegra`, L4T 36.4.3, CUDA 12.6.
- Direct Ethernet: Windows `10.42.0.70/24` to NX `10.42.0.2/24`; 1 ms ping and SSH pass.
- ROS 2 Humble is installed but was not sourced in the audit shell.
- Attached RealSense is the intended D435, PID `8086:0b07`, serial `943623021659`, at USB 3 / 5 Gbps.
- Six V4L2 video nodes exist. No HID/IIO IMU is expected because D435 has no internal IMU. Root disk has 17 GiB free (86% used).
- The `nvidia` user has verified read/write access to the D435 video nodes.
- Current apt sources have ROS RealSense wrapper packages, but no `librealsense2-*` runtime, development, or viewer package.
- librealsense v2.58.4 RSUSB library and tools are installed at `/home/nvidia/opt/librealsense-2.58.4`; no DKMS, kernel, BSP, or system package was changed.
- RSUSB enumeration is blocked by raw `/dev/bus/usb` access permissions. The V4L2 no-root alternative is installed at `/home/nvidia/opt/librealsense-v4l2-2.58.4` and detects D435 serial `938422073656`, firmware `5.17.3.10`.
- Stereo IR timing at 640×480@30 is PASS: 1799 frame sets in 60 s, 29.983 FPS per stream, no duplicate/backward timestamps, 0 ms maximum left-right delta, 1.645% process CPU, and 21.3 MiB peak RSS.

## Inferred Facts

- L4T 36.4.3 is the JetPack 6.2 baseline.

## Unknown Facts

- RMW when ROS is sourced; D435 stereo acquisition/timing performance; PX4 IMU availability.

## Development Host

Windows source of truth and WSL Ubuntu 22.04.4; GitHub SSH works.

## Jetson NX Environment

See `docs/phases/phase0_nx_environment_audit.md`.

## D435 State

VERIFIED: D435 is connected at USB 3 / 5 Gbps. Stereo IR acquisition/timing at 640×480@30 is PASS.

## VIO State

Pure Stereo VO ROS 2 adapter now builds and passed a ground smoke test with the D435 IR pair. PX4 stereo-inertial VIO is a later stage.

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

Phase A is complete. Pure Stereo VO baseline is not deployed.

## Failed Attempts

The old address `10.33.154.71` is stale; do not reuse it.

No failed experiment in the revised route. The former camera-model mismatch was a documentation error corrected by this checkpoint.

## Do Not Repeat

- Do not search for a D435 internal IMU; VIO will use PX4 IMU later.
- Do not enable RGB, depth, or point clouds in the first stereo acquisition test.
- Do not install a DKMS package, modify BSP/L4T, or install packages before a minimal-risk dependency plan is approved.
- Do not commit credentials or private keys.

## Risks

Root disk is 86% full; avoid large downloads, builds, datasets, and rosbags.

## Next Recommended Step

Select and assess one Pure Stereo VO baseline (ORB-SLAM3 Stereo is the first candidate) without deploying multiple algorithms.

## Exact Next Commands

Use `LD_LIBRARY_PATH=/home/nvidia/opt/librealsense-v4l2-2.58.4/lib` for the benchmark runtime.

## Files Changed

Phase 0 report and state documentation.

## Latest Test Results

Phase 0: PASS. Phase A: PASS. Phase B Pure Stereo VO: NOT STARTED.

## Rollback Information

To restore host Ethernet, set `以太网 4` to `192.168.0.200/24` with no gateway. Git changes are documentation only.
