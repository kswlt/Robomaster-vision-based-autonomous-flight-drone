# Project Handoff

> **2026-09-07 update (VIO)**: ORB-SLAM3 **tight-coupled RGB-D+IMU VIO (IMU_RGBD mode) is enabled and the post-init crash is fixed**. The root cause was IMU timestamps ~20 ms ahead of image timestamps (image capture latency), which made ORB-SLAM3's `PreintegrateIMU()` extract only 1 IMU point → `Empty IMU measurements vector!!!` → NaN/SO3::exp abort or segfault. Fix: subtract 0.025 s from IMU timestamps in the wrapper so IMU stamps are slightly earlier than image stamps. Extrinsic `IMU.T_b_c1` = camera→IMU (FLU→OpenCV axis permutation `[[0,0,1],[-1,0,0],[0,-1,0]]`). VIO now initializes (500+ map points) and runs stably without crashing; gravity alignment (roll/pitch≈0) and direction correspondence pending verification in a textured scene. Earlier: Astra Pro RGB-D input verified, ground RGB-D VO smoke passed, PX4 EKF2 vision-position fusion verified (step 6 done). Calibration skipped per user decision. Source of truth: `docs/CURRENT_STATE.md` + `docs/PROJECT_PROMPT_ZH.md`.

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
- camera_info published (fx=fy=570.342, 640×480, zero distortion) but cx/cy = exact image center → **likely defaults; calibration skipped by user decision**.
- **RGB-D VO smoke passed**: new `rgbd_node` (ORB-SLAM3 RGBD mode, message_filters sync of rgb8+16UC1, config `astra_rgbd.yaml` with `RGBD.DepthMapFactor=1000`, `Stereo.ThDepth=40`, `Stereo.b=0`). Static-scene 45 s run: tracking_state=2, pose ~21–25 FPS, mean ~30 ms/frame, ~1300 frames, 1 map reset, 0 LOST. Pure-VO smoke only (no IMU/GT).
- **RGB-D+IMU VIO enabled (IMU_RGBD mode)**: `rgbd_node` extended with `/imu/data` subscription (RELIABLE QoS), IMU measurement buffer (deque+mutex, 5 s), `System::IMU_RGBD` sensor type, `TrackRGBD(im,depth,ts,vImu)`. Config `astra_rgbd_imu.yaml` with IMU noise params (EuRoC defaults: gyro_noise=1.7e-4, acc_noise=2e-3, gyro_walk=1.7e-5, acc_walk=3e-3, freq=200), `IMU.fastInit=1` (skip acceleration >0.5 m/s² init threshold), extrinsic `IMU.T_b_c1`.
- **VIO crash root cause & fix**: IMU stamps (ROS now) were ~20 ms ahead of image stamps (capture latency). ORB-SLAM3 `PreintegrateIMU()` extracts IMU points with `t < current_frame.t - mImuPer`; IMU-ahead caused the first point to hit the else-branch (push + break), leaving `mvImuFromLastFrame` with 1 point → n=0 → `Empty IMU measurements vector!!!` → preintegration fails → `SO3::exp(omega=NaN)` abort or segfault. **Fix: subtract 0.025 s from IMU timestamp in `onImu` callback.** Post-fix: VIO initializes (500+ map points), runs stably for minutes with 0 LOST, no crash.
- **VIO extrinsic**: PX4-forwarded IMU is **FLU** (static z≈-9.81, x≈0.34 bias), ~193 Hz. `IMU.T_b_c1` = camera→IMU transform (ORB-SLAM3 `mTcb` definition): axis permutation `[[0,0,1],[-1,0,0],[0,-1,0]]` (IMU_x=camera_z_forward, IMU_y=-camera_x, IMU_z=-camera_y). Parameter name is `IMU.T_b_c1` (NOT `IMU.T_b_c`).
- **VIO pending**: gravity alignment (roll/pitch should ≈0), direction correspondence with airframe (VIO only aligns roll/pitch; yaw remains arbitrary, unified by EKF2 fusion), long-term stability (pure-VO had ~44 min NaN abort; VIO needs retest). Poor scenes (dark/textureless/invalid depth) cause LOST + auto-reset, expected behavior.
- **PX4 vision fusion verified (step 6)**: firmware is the **2025+ new EKF2 parameter set** — `EKF2_EV_CTRL` (bit0 h-pos / bit1 v-pos / bit2 vel / bit3 yaw) exists, legacy `EKF2_AID_MASK`/`SYS_MC_EST_GROUP`/`MAV_ODOM` absent. Observed `EKF2_EV_CTRL=15` (int; read as 2.1e-44 via float bit-pattern in PARAM_VALUE) = all vision bits on (likely auto-migrated from the D435-era AID_MASK). `EKF2_EV_POS_{X,Y,Z}=0`, `EKF2_EVP_NOISE=EVV_NOISE=0.1`, gates 5/3. Bridge: `/home/nvidia/fly/vio_benchmark/scripts/run/px4_fusion_bridge.py` (source of truth copy also at `C:\Users\Admin\DoubaoWork\chats\2026-09-06\new-chat\px4_fusion_bridge.py`): `/orb_slam3/pose` → ENU→NED → MAVLink ODOMETRY (LOCAL_NED, pos cov 0.01 m²) + HIGHRES_IMU 250 Hz → `/imu/data` + ESTIMATOR_STATUS 5 Hz monitor. 60 s run: EKF transitioned const_pos_mode(0xe5) → vision absolute pos fusion (0x37f: pos_horiz_abs=1, const_pos=0, vel_h=1); innovation ratios pos_h 0.01–0.02, pos_v 0.01, vel 0.00 (gate 1.0) — accepted smoothly. IMU ~195 Hz, ODOMETRY ~23 Hz, VO 1881 frames 0 LOST, device alive.
- **pymavlink pitfalls fixed in the bridge** (recurring): (1) int32 params arrive as float bit-patterns in `param_value` — decode by `param_type` (2.1e-44=15, 2.8e-45=2); (2) this dialect's `estimator_status` is legacy MAVLink1 (10 fields, flags ≤ bit10, no vision bits / no innovation_metric) — fusion judge via `const_pos`(bit7)+`pos_horiz_abs`(bit4)+`pred_pos_abs`(bit9); (3) PX4 new firmware intermittently emits messages pymavlink's `add_message` cannot register (crashes) — monkey-patched to skip bad messages; (4) PX4 never sends TIMESYNC unprompted — bridge must `timesync_send` first; injected ODOMETRY timestamp = local + offset (offset = PX4 − local clock).
- Board model string (observed): `NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super` (coexists with the documented "Orin NX" naming; user to confirm).
- USB topology: Astra Pro behind a 2-level unpowered hub chain (Genesys 0608 → 0610). Margins are poor: one hard drop on depth start (dmesg: `Cannot enable`, `tegra-xusb buffer overrun`, `disabled by hub (EMI?)`) required physical re-plug; stable since. Recommend direct connect or powered hub before flight tests.

## Operational Lessons (do not repeat mistakes)

- **Always `pkill -9 -f standalone_container` before/after tests**: `ros2 component standalone` spawns a container child that survives the parent python's exit; stale containers cause `Resource busy` on open and fake "device disconnect" cycles (they fight over the same device). This was misread as hardware instability for one full test round.
- Do not reuse D435 pipelines/calibration/parameters for the Astra.
- Do not search for a D435 internal IMU; VIO uses PX4 IMU.
- Do not commit credentials or private keys.

## Current Blocker / Next Step

No blocker on input/VO/fusion/VIO side anymore. VIO is enabled and crash-free. **Next: verify VIO gravity alignment and direction correspondence in a textured scene**, then authorized low-risk hover test (step 7) — props off, user in the loop; never auto-arm/takeoff. Before hover: (1) re-check fusion innovation under real motion (static-only verified so far); (2) VIO long-term stability retest; (3) confirm acceptance of `EKF2_EV_POS_*=0` (no extrinsic calibration); (4) user confirms three PX4 safety params via QGC (`CBRK_FLIGHTTERM=121212` flight termination disabled, `COM_LOW_BAT_ACT=0` no low-bat action, `MPC_THR_HOVER=0.5` default uncalibrated). Always `fuser /dev/ttyACM0` before opening the serial port.

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

Astra Pro depth+color → `astra_camera` (ROS 2) → ORB-SLAM3 `rgbd_node` (RGB-D VO, smoke-passed) → PX4-IMU fusion → A/B benchmark → impact-aware recovery supervisor. (D435 Pure Stereo path is legacy only.)

## Risks

- Root disk ~16 GiB free; avoid large downloads/builds/rosbags.
- USB hub chain electrical marginality (see above) — verify stability over longer runs; prefer physical topology fix.
- Default intrinsics / no depth-color extrinsics calibration (user decision): acceptable for VO smoke; if trajectory diverges in real motion, revisit calibration.
