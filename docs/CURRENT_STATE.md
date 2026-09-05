# Current State

- Current phase: Phase B — Pure Stereo VO baseline.
- Status: IN_PROGRESS; Phase 0 and Phase A are completed and verified.
- Repository and GitHub: source path verified; GitHub SSH reachable.
- WSL: Ubuntu 22.04.4; required repository mount verified.
- NX: `nvidia-sentry`; Ubuntu 22.04.5; kernel 5.15.148-tegra; L4T 36.4.3; CUDA 12.6; 17 GiB root free.
- NX SSH: wired `10.42.0.2`; host USB GbE `10.42.0.70/24`; public-key access verified.
- ROS 2: Humble installed but not sourced; RMW unknown. No librealsense apt package is available. User-space librealsense v2.58.4 V4L2 is verified at `/home/nvidia/opt/librealsense-v4l2-2.58.4`.
- Camera: D435 (`8086:0b07`, serial `943623021659`) at USB 3 / 5 Gbps; video nodes present. Internal IMU: not present by hardware design.
- Stereo acquisition/timing: PASS at 640×480@30 for 60 s (29.983 FPS each, no duplicate/backward timestamps, max 0 ms stereo delta, 1.645% CPU, 21.3 MiB peak RSS). Pure Stereo VO, PX4 IMU, VIO, depth, and impact recovery: not deployed or tested.
