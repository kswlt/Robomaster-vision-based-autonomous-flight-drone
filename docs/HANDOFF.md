# Project Handoff

## Last Updated

2026-09-05

## Current Goal

Resolve the camera hardware mismatch before D435i stereo-inertial capture validation.

## Current Phase

Phase 0 complete — awaiting correct D435i hardware before Phase 1.

## Current Status

PASS (Phase 0); BLOCKED (Stereo-Inertial VIO progression)

## What Was Just Done

Re-enumerated the connected RealSense after a request to continue; it remains the same D435 and still exposes no IMU nodes.

## Verified Facts

- NX: `nvidia-sentry`, Ubuntu 22.04.5, kernel `5.15.148-tegra`, L4T 36.4.3, CUDA 12.6.
- Direct Ethernet: Windows `10.42.0.70/24` to NX `10.42.0.2/24`; 1 ms ping and SSH pass.
- ROS 2 Humble is installed but was not sourced in the audit shell.
- Attached RealSense is D435, PID `8086:0b07`, serial `943623021659`, at USB 3 / 5 Gbps.
- Six V4L2 video nodes exist; HID/IIO IMU nodes do not. Root disk has 17 GiB free (86% used).

## Inferred Facts

- L4T 36.4.3 is the JetPack 6.2 baseline.

## Unknown Facts

- RMW when ROS is sourced; D435i state because no D435i is connected.

## Development Host

Windows source of truth and WSL Ubuntu 22.04.4; GitHub SSH works.

## Jetson NX Environment

See `docs/phases/phase0_nx_environment_audit.md`.

## D435i State

BLOCKED: attached hardware is D435, not D435i, and has no IMU interface.

## VIO State

Not deployed; blocked pending correct hardware.

## Depth State

Not tested; D435 depth-only validation needs explicit scope approval.

## Runtime Architecture

Intended: D435i left/right IR + IMU → Stereo-Inertial VIO → pose/velocity. The current D435 exposes video only.

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

HW-001: D435 is attached, not D435i.

## Failed Attempts

The old address `10.33.154.71` is stale; do not reuse it.

Re-checking the current camera does not unblock Phase 1: USB descriptor remains D435 PID `8086:0b07`, serial `943623021659`, with no HID or IIO IMU node.

## Do Not Repeat

- Do not treat D435 video nodes as D435i IMU availability.
- Do not install librealsense, modify BSP/L4T, or start VIO before hardware is resolved.
- Do not commit credentials or private keys.

## Risks

Root disk is 86% full; avoid large downloads, builds, datasets, and rosbags.

## Next Recommended Step

Connect the intended D435i, then repeat USB/HID/librealsense enumeration before Phase 1.

## Exact Next Commands

On NX after attaching D435i: `lsusb; lsusb -t; ls -l /dev/video* /dev/hidraw*`.

## Files Changed

Phase 0 report and state documentation.

## Latest Test Results

Phase 0: PASS. D435i suitability: BLOCKED.

## Rollback Information

To restore host Ethernet, set `以太网 4` to `192.168.0.200/24` with no gateway. Git changes are documentation only.
