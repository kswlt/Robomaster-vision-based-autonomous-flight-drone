# RoboMaster 视觉自主飞行无人机：当前项目提示词

你正在维护一个运行在 Jetson Orin NX + CUAV X7Pro PX4 上的视觉自主飞行项目。请严格以以下实测状态为准，不要把历史 D435 配置当作当前硬件配置。

## 当前电脑与连接

- Windows 工作区：`C:\Users\Admin\Desktop\无人机\Robomaster-vision-based-autonomous-flight-drone`
- NX 主机：`nvidia-sentry`，Ubuntu 22.04.5，L4T 36.4.3，kernel 5.15.148-tegra，CUDA 12.6。
- 当前优先连接方式是 Wi-Fi：NX `192.168.1.53/23`，SSID `ADAM_5G`。Windows 端执行：

```powershell
ssh -i C:\Users\Admin\.ssh\robomaster_nx_audit nvidia@192.168.1.53
```

- 旧网线链路 NX `enP8p1s0=10.42.0.2/24` 当前为 DOWN；只有用户确认重新插好网线并看到链路 UP 后，才使用该地址。
- 不要读取、复制或提交 SSH 私钥；私钥只留在 Windows 的 `C:\Users\Admin\.ssh\`。

## 当前硬件事实

- 飞控：CUAV X7Pro，PX4 1.15.2；NX 上稳定串口为 `/dev/serial/by-id/usb-CUAV_PX4_CUAV_X7Pro_0-if00`（实际指向 `/dev/ttyACM0`）。
- 相机：实际识别为 Orbbec Astra Pro，USB IDs `2bc5:0502`（RGB，`/dev/astra_pro_rgb`）、`2bc5:0403`（深度，`/dev/astra_pro`）。
- **驱动已验证（2026-09-06/07）**：官方 OrbbecSDK（v1.10.27/v1.10.35/源码）已移除原版 Astra Pro（PID 0403），改用社区路线 `Es777777/astra-pro-ros2`（legacy astra_camera，libuvc+OpenNI2），工作空间 `/home/nvidia/astra_pro_ws`。
- **深度流已验证**：640×480@30、16UC1、~29.7 FPS 稳定；原始值即毫米（×0.001→米）。
- **彩色流已验证**：640×480 MJPG（`uvc_camera.pid:=0x0502`），~19–20 FPS。
- **话题**：`/camera/depth/{image_raw,camera_info}`、`/camera/color/{image_raw,camera_info}`、`/camera/extrinsic/depth_to_color`。
- camera_info 已发布但 cx/cy 恰为图像中心，**疑似默认值，RGB-D 标定仍是必做项**；不得使用 D435 的标定、分辨率、曝光或 librealsense 参数。
- 运行纪律：测试前后必须 `pkill -9 -f standalone_container`，否则残留容器会报 `Resource busy` 并造成伪掉线。
- `vio-watchdog.service` 会自动重启旧版相机/IMU/MAVLink 进程；任何新程序打开 PX4 串口前，必须先检查是否已有进程占用 `/dev/ttyACM0`。

## 工作目标与执行顺序

目标是先实现可靠的视觉定位和稳定悬停，再考虑更高阶功能；不自动解锁、不自动起飞、不自动切换飞行模式。

1. ~~在 NX 上安装并验证适配 Astra Pro 的 Orbbec SDK 或 ROS 2 驱动~~ ✅ 已完成：`astra_camera`（libuvc 社区路线）编译并验证。
2. ~~枚举并记录 RGB、Depth 的真实 profile、帧率、设备序列号、时间戳和深度尺度~~ ✅ 已完成：深度 640×480@30 / 16UC1 / 29.7 FPS / 毫米尺度（0.001）；彩色 640×480 MJPG ~20 FPS。
3. 获取/校验 Astra Pro RGB-D 内参、外参、畸变和深度尺度；**重新生成项目自己的标定文件**（当前缺口；camera_info 疑似默认值）。
4. 发布 ROS 2 图像/深度/相机信息，并接入 Foxglove（桥接端口 `8765`，桥已在运行，需确认 `/camera/*` 话题可见）。
5. 先做地面 RGB-D VO，再做不依赖相机 IMU 的 VIO；报告跟踪质量、有效位姿、速度和重置次数。
6. 通过 PX4 MAVLink `ODOMETRY`/等效视觉里程计接口发送经过时间戳和坐标系核对的数据；在地面站确认 `vehicle_visual_odometry`、`vehicle_local_position` 和 EKF 外部视觉融合状态。
7. 仅在螺旋桨拆下、定位连续稳定、方向/高度/失效保护均验证后，安排人工授权的低风险悬停测试。

## 必须执行的检查

```bash
ip -br addr
lsusb
ls -l /dev/video* /dev/serial/by-id/
ps -ef | grep -E 'mavlink|vio|camera|foxglove' | grep -v grep
systemctl status vio-watchdog.service --no-pager
```

PX4 NSH 中使用：

```text
listener vehicle_visual_odometry 5
listener vehicle_local_position 5
listener estimator_status_flags 5
commander status
```

持续观察请在 NSH 中执行 `listener vehicle_visual_odometry`（退出用 Ctrl+C）；不要把“topic 能看到”误判成“数据有效”。必须同时确认时间戳新鲜、位置/速度不是 NaN、质量和 EKF 融合标志符合预期。

## 安全与文档纪律

- 不自动 arm、takeoff、切换模式或绕过 PX4 解锁检查；所有飞行操作由用户在现场人工确认。
- 不在没有深度流和重新标定的情况下启动 RGB-D VO/VIO，更不能直接起飞。
- 每次硬件、驱动、串口或参数变化都更新 `docs/CURRENT_STATE.md`、`docs/HANDOFF.md` 和对应环境记录。
- 代码修改后运行 `git diff --check`，提交清晰的 Git commit，并推送到 `origin/main`；绝不提交密钥、日志中的密码或临时缓存。
