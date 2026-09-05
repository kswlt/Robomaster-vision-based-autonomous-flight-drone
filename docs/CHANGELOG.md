# Changelog

## 2026-09-05

- Initialized the multi-agent repository documentation and Phase 0 handoff state.
- Recorded blocked NX wired-network connectivity: host USB GbE is `192.168.0.200/24`; the documented NX address `10.33.154.71` is unreachable.
- With user authorization, aligned the host USB GbE adapter to `10.33.154.70/24` without a default gateway; the target still has no ARP response, so Phase 0 remains blocked.
- Discovered a reachable IPv6 link-local SSH endpoint on the direct Ethernet link; documented the interactive-authentication verification step.
- Completed Phase 0 NX/WSL/D435 audit; corrected direct NX IP to `10.42.0.2` and recorded the former camera-model documentation issue.
- Reconfirmed that the currently connected RealSense remains D435 without an IMU interface; Phase 1 remains blocked.
- Corrected D435 hardware documentation and changed the roadmap to Stereo VO → PX4-IMU VIO → A/B benchmark → impact-aware recovery.
- Assessed librealsense availability for Phase A; configured apt sources lack the required runtime package.
- Built a user-space librealsense v2.58.4 RSUSB variant; documented raw-USB permission block and V4L2-backend fallback.
- Completed V4L2 user-space librealsense v2.58.4 build and D435 enumeration without system-level changes.
- Added and passed the first 60-second D435 stereo IR timing benchmark.
