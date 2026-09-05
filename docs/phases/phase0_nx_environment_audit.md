# Phase 0: NX Environment Audit

Status: PASS — read-only audit complete. Progression to D435i stereo-inertial capture is BLOCKED by the attached camera hardware.

## Development Host

- Repository: `C:\Users\Admin\Desktop\无人机\Robomaster-vision-based-autonomous-flight-drone` — VERIFIED.
- WSL: Ubuntu 22.04.4 LTS, kernel `6.18.33.2-microsoft-standard-WSL2`; required repository mount exists — VERIFIED.
- GitHub SSH and `origin/main` access — VERIFIED.

## NX Environment

| Item | State | Evidence |
| --- | --- | --- |
| Hostname / architecture | VERIFIED | `nvidia-sentry`, `aarch64` |
| OS / Kernel / L4T | VERIFIED | Ubuntu 22.04.5; `5.15.148-tegra`; R36.4.3 |
| JetPack | INFERRED | JetPack 6.2 baseline from L4T 36.4.3 |
| CUDA | VERIFIED | Driver 540.4.0, CUDA 12.6 |
| CPU / RAM | VERIFIED | 6 ARMv8 cores; 7.4 GiB RAM, 5.5 GiB available |
| Root disk | VERIFIED | 116 GiB total, 94 GiB used, 17 GiB free (86% used) |
| Baseline load | VERIFIED | CPU 0–5%, GPU 0%, RAM 1.86 GiB used, input power ~4.4 W |
| Toolchain | VERIFIED | Python 3.10.12; GCC/G++ 11.4.0; CMake 3.22.1; Git 2.34.1 |

## Networking, ROS, and Camera

- NX wired: `enP8p1s0`, `10.42.0.2/24`, UP; host USB GbE: `10.42.0.70/24`, no gateway, 1 Gbps — VERIFIED.
- Wired ping is 1 ms; public-key SSH works. Previous `10.33.154.71` target is obsolete — VERIFIED.
- ROS Humble exists at `/opt/ros/humble`, but it was not sourced in the audit shell; RMW is UNKNOWN.
- librealsense tools and libraries are absent — VERIFIED.
- Camera: Intel `8086:0b07`, product `RealSense D435`, serial `943623021659`; six V4L2 video nodes and USB 3 / 5 Gbps — VERIFIED.
- No `/dev/hidraw*`, IIO devices, or HID sensor modules — VERIFIED.

## Conclusion

The attached device is D435, not D435i, and cannot provide the IMU required by the current Stereo-Inertial VIO scope. Do not start Phase 1/2 or install librealsense until a D435i is connected, unless a D435 depth-only scope is explicitly approved. Root storage is 86% full; avoid large downloads, builds, or rosbags. Do not alter L4T, CUDA, kernel, boot, or BSP components.
