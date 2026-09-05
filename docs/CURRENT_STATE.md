# Current State

- Current phase: Phase A — D435 stereo IR acquisition and timing validation.
- Status: IN_PROGRESS; Phase 0 remains completed and verified.
- Repository and GitHub: source path verified; GitHub SSH reachable.
- WSL: Ubuntu 22.04.4; required repository mount verified.
- NX: `nvidia-sentry`; Ubuntu 22.04.5; kernel 5.15.148-tegra; L4T 36.4.3; CUDA 12.6; 17 GiB root free.
- NX SSH: wired `10.42.0.2`; host USB GbE `10.42.0.70/24`; public-key access verified.
- ROS 2: Humble installed but not sourced; RMW unknown. librealsense absent and no `librealsense2-*` apt package is available in configured sources.
- Camera: D435 (`8086:0b07`, serial `943623021659`) at USB 3 / 5 Gbps; video nodes present. Internal IMU: not present by hardware design.
- Stereo acquisition and timing: not yet validated. Pure Stereo VO, PX4 IMU, VIO, depth, and impact recovery: not deployed or tested.
