# Current State

- Current phase: Phase 0 complete — awaiting correct D435i hardware before Phase 1.
- Status: PASS for Phase 0; BLOCKED for stereo-inertial VIO progression.
- Repository and GitHub: source path verified; GitHub SSH reachable.
- WSL: Ubuntu 22.04.4; required repository mount verified.
- NX: `nvidia-sentry`; Ubuntu 22.04.5; kernel 5.15.148-tegra; L4T 36.4.3; CUDA 12.6; 17 GiB root free.
- NX SSH: wired `10.42.0.2`; host USB GbE `10.42.0.70/24`; public-key access verified.
- ROS 2: Humble installed but not sourced; RMW unknown. librealsense absent.
- Camera: D435 (`8086:0b07`, serial `943623021659`) at USB 3 / 5 Gbps; video nodes present; IMU nodes absent.
- OpenVINS and depth modes: not deployed or tested.
