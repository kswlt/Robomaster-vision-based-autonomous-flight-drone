# Project Handoff

> **2026-09-07 update**: Astra Pro RGB-D input is now **driven and verified** (depth 640×480@30 stable + color MJPG verified). The historical D435 / Pure Stereo VO sections below are retained for traceability only. Source of truth: `docs/CURRENT_STATE.md` + `docs/PROJECT_PROMPT_ZH.md`.

## Active Hardware and Connection

- NX hostname: `nvidia-sentry`; Wi-Fi address: `192.168.1.53/23` on `ADAM_5G`.
- Windows SSH: `ssh -i C:\Users\Admin\.ssh\robomaster_nx_audit nvidia@192.168.1.53`.
- Former direct Ethernet `10.42.0.2` is unavailable (`enP8p1s0` down).
- PX4 CUAV X7Pro: `/dev/ttyACM0` (stable path `/dev/serial/by-id/usb-CUAV_PX4_CUAV_X7Pro_0-if00`).
- Camera: Orbbec Astra Pro — depth `2bc5:0403` (`/dev/astra_pro`), RGB FHD `2bc5:0502` (`/dev/astra_pro_rgb`).

## Driver Bring-up — VERIFIED (2026-09-06/07)

- **Official OrbbecSDK route is dead for the original Astra Pro**: v1.10.27/v1.10.35 and current source removed PID 0403 (SDK enumerates 0 devices). Do not attempt it again.
- **Working route**: `Es777777/astra-pro-ros2` (legacy `astra_camera`, libuvc + bundled OpenNI2 redist), validated for Astra Pro on ROS 2 Humble / Ubuntu 22.04.
- Workspace: `/home/nvidia/astra_pro_ws` — `astra_camera` + `astra_camera_msgs` built (needs `-DCMAKE_PREFIX_PATH=/home/nvidia/opt/magic_enum_install`).
- Deps (apt): libuvc-dev, libgoogle-glog-dev, ros-humble-camera-info-manager, ros-humble-image-publisher. magic_enum 0.9.8 installed under `/home/nvidia/opt/magic_enum_install` (add symlink `include/magic_enum.hpp -> include/magic_enum/magic_enum.hpp`).
- udev: vendor `99-obsensor-libusb.rules` installed + appended 0502 entry; both devices MODE 0666.
- Launch: `ros2 component standalone astra_camera astra_camera::OBCameraNodeFactory -n camera --node-namespace /camera -p enable_depth:=true -p depth_width:=640 -p depth_height:=480 -p depth_fps:=30 -p enable_color:=true -p color_width:=640 -p color_height:=480 -p color_fps:=30 -p uvc_camera.enable:=true -p uvc_camera.vid:=0x2bc5 -p uvc_camera.pid:=0x0502 -p uvc_camera.format:=mjpeg -p number_of_devices:=1` (env: source ROS + workspace; `LD_LIBRARY_PATH` += `.../openni2_redist/arm64`).

## Verified Facts (2026-09-06/07)

- Depth stream: 640×480@30, 16UC1, ~29.7 FPS sustained >75 s, no drops/errors, device stable.
- Depth units: raw uint16 = millimeters (sample vmin 4557 / vmax 9859 / vmean 7126); scale 0.001 → meters (`ROS_DEPTH_SCALE=0.001`).
- Color stream: 640×480 MJPG, ~19–20 FPS (USB-chain-limited).
- Topics: `/camera/depth/{image_raw,camera_info}`, `/camera/color/{image_raw,camera_info}`, `/camera/extrinsic/depth_to_color`.
- camera_info published (fx=fy=570.342, 640×480, zero distortion) but cx/cy = exact image center → **likely defaults; real calibration still required**.
- Board model string (observed): `NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super` (coexists with the documented "Orin NX" naming; user to confirm).
- USB topology: Astra Pro behind a 2-level unpowered hub chain (Genesys 0608 → 0610). Margins are poor: one hard drop on depth start (dmesg: `Cannot enable`, `tegra-xusb buffer overrun`, `disabled by hub (EMI?)`) required physical re-plug; stable since. Recommend direct connect or powered hub before flight tests.

## Operational Lessons (do not repeat mistakes)

- **Always `pkill -9 -f standalone_container` before/after tests**: `ros2 component standalone` spawns a container child that survives the parent python's exit; stale containers cause `Resource busy` on open and fake "device disconnect" cycles (they fight over the same device). This was misread as hardware instability for one full test round.
- Do not reuse D435 pipelines/calibration/parameters for the Astra.
- Do not search for a D435 internal IMU; VIO uses PX4 IMU.
- Do not commit credentials or private keys.

## Current Blocker / Next Step

No blocker on the input side anymore. **Next: RGB-D calibration (step 3)** — verify/measure color intrinsics, depth–color extrinsics, distortion; produce project calibration files; then wire `/camera/*` topics to Foxglove (:8765, bridge already running) and start ground RGB-D VO (step 5). Do not launch any new process that opens `/dev/ttyACM0` without checking current occupancy (`vio-watchdog.service` runs the IMU bridge on it).

## Last Updated

2026-09-07

## Current Goal

Bring up Orbbec Astra Pro RGB-D input (done: driver + depth + color verified) → calibration → ground RGB-D VO/VIO → PX4 fusion → authorized low-risk hover.

## Current Phase

Hardware transition — Astra Pro RGB-D bring-up (Phase B), calibration next.

## Current Status

IN_PROGRESS (Phase B); Phase A and Phase 0 are PASS.

## Development Host

Windows source of truth; GitHub SSH works (`git@github.com:kswlt/...`).

## Important Paths

- Repository: `C:\Users\Admin\Desktop\无人机\Robomaster-vision-based-autonomous-flight-drone`
- NX camera workspace: `/home/nvidia/astra_pro_ws` (build with `-DCMAKE_PREFIX_PATH=/home/nvidia/opt/magic_enum_install`)
- NX test scripts: `/home/nvidia/astra_pro_ws/*.sh` (stage/clean/color/info/probe)

## Runtime Architecture

Astra Pro depth+color → `astra_camera` (ROS 2) → RGB-D VO/VIO → PX4-IMU fusion → A/B benchmark → impact-aware recovery supervisor. (D435 Pure Stereo path is legacy only.)

## Risks

- Root disk ~16 GiB free; avoid large downloads/builds/rosbags.
- USB hub chain electrical marginality (see above) — verify stability over longer runs; prefer physical topology fix.
