# Current State

- 当前阶段：硬件切换与 RGB-D 输入恢复；**Astra Pro 深度/彩色流已驱动并验证**，进入标定阶段。
- 状态：IN_PROGRESS（Phase B）；深度流可用，RGB-D 标定与 VO/VIO 尚未完成。
- Windows 工作区：`C:\Users\Admin\Desktop\无人机\Robomaster-vision-based-autonomous-flight-drone`；GitHub SSH 已验证。
- NX：`nvidia-sentry`，Ubuntu 22.04.5，kernel 5.15.148-tegra，L4T 36.4.3，CUDA 12.6。板卡 model 串实测：`NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super`（与既有文档中 Orin NX 命名并存，待用户确认后再统一）。
- 当前连接：NX Wi-Fi `wlP1p1s0=192.168.1.53/23`（ADAM_5G）；旧有线链路 `enP8p1s0=10.42.0.2/24` 仍为 DOWN。
- NX SSH：`ssh -i C:\Users\Admin\.ssh\robomaster_nx_audit nvidia@192.168.1.53`；私钥不进入仓库。
- PX4：CUAV X7Pro，`/dev/ttyACM0`，稳定路径 `/dev/serial/by-id/usb-CUAV_PX4_CUAV_X7Pro_0-if00`。

## 相机（Orbbec Astra Pro）驱动状态 — 已验证

- **官方 OrbbecSDK 路线已确认死亡**：v1.10.27（稳定）、v1.10.35（预发布）及 GitHub 源码均**移除了原版 Astra Pro（PID 0403）**，SDK 枚举不到设备。
- **采用社区路线并验证成功**：`Es777777/astra-pro-ros2`（legacy `astra_camera`，基于 libuvc + 内置 OpenNI2 redist），ROS 2 Humble 实机验证过 Astra Pro。
- 工作空间：`/home/nvidia/astra_pro_ws`（`astra_camera` + `astra_camera_msgs` 编译成功，2026-09-06）。
- 依赖：libuvc-dev、libgoogle-glog-dev、ros-humble-camera-info-manager、ros-humble-image-publisher（apt）；magic_enum 0.9.8 用户空间安装于 `/home/nvidia/opt/magic_enum_install`（构建需 `-DCMAKE_PREFIX_PATH=/home/nvidia/opt/magic_enum_install`）。
- udev 规则：已安装厂商 `99-obsensor-libusb.rules`，并追加 0502 条目；`/dev/astra_pro`（0403）、`/dev/astra_pro_rgb`（0502）均 0666。
- **深度流已验证**：640×480@30，16UC1，`~29.7 FPS` 持续 75 s 以上无掉帧无错误，设备存活。
- **彩色流已验证**：640×480 MJPG，`~19–20 FPS`（受链路余量限制），需 `uvc_camera.pid:=0x0502`（非仓库默认 0x0501）。
- **深度尺度**：16UC1 原始值即毫米（实测 vmin 4557 / vmax 9859 / vmean 7126），换算 0.001 → 米；驱动常量 `ROS_DEPTH_SCALE=0.001`。
- **话题**：`/camera/depth/{image_raw,camera_info}`、`/camera/color/{image_raw,camera_info}`、`/camera/extrinsic/depth_to_color`。
- **camera_info**：已发布（fx=fy=570.342，640×480，plumb_bob 零畸变），但 cx=319.5/cy=239.5 恰为图像中心，**疑似默认占位而非实测标定**——RGB-D 标定仍为必做项。
- **运行注意**：`ros2 component standalone` 的容器子进程不会随外层 python 退出，必须 `pkill -f standalone_container` 清理；残留容器会报 `Resource busy` 并互相抢设备造成"伪掉线"。

## 硬件注意事项（重要）

- Astra Pro 当前仍挂在**两级无源 USB Hub 链**（0608→0610）上，电气余量不足：曾发生深度流启动后整链掉线（dmesg：`Cannot enable`、`buffer overrun`、`disabled by hub (EMI?)`），需物理重插才恢复。
- 重插后深度+彩色双流已稳定运行；**生产/悬停测试前建议直连 NX USB 口或改用供电 Hub**。
- RGB 的 uvcvideo 驱动曾在测试中解绑（`unbind`），重启后会自动重新绑定；libuvc 走 `/dev/astra_pro_rgb` 不受影响。

## 当前服务

- `vio-watchdog.service` 运行旧版链路（foxglove_relay/hik_camera、imu_mavlink_bridge 占用 `/dev/ttyACM0`、foxglove_bridge :8765）。新 MAVLink 程序不得与其争用 `/dev/ttyACM0`。

## 下一步（按 PROJECT_PROMPT_ZH 顺序）

1. **标定（第 3 步，当前缺口）**：获取/校验 Astra Pro 彩色内参、深度-彩色外参、畸变，生成项目自有标定文件，替换默认 camera_info。
2. **Foxglove 接入（第 4 步）**：确认 `/camera/*` 话题经 :8765 桥在 Foxglove 可见（桥已在运行，自动发现话题）。
3. **地面 RGB-D VO（第 5 步）**：先做不依赖相机 IMU 的 VO/VIO，报告跟踪质量、有效位姿、速度、重置次数。
4. **PX4 融合（第 6 步）**：MAVLink ODOMETRY 注入，地面站核对 EKF 视觉融合状态。
5. **悬停测试（第 7 步）**：拆桨 + 人工授权；不自动解锁/起飞。
