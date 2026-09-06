# Current State

- 当前阶段：硬件切换与 RGB-D 输入恢复；D435 旧路线仅作历史基线。
- 状态：IN_PROGRESS；当前尚未具备可用于 RGB-D VO/VIO 的深度流。
- Windows 工作区：`C:\Users\Admin\Desktop\无人机\Robomaster-vision-based-autonomous-flight-drone`；GitHub SSH 已验证。
- NX：`nvidia-sentry`，Ubuntu 22.04.5，kernel 5.15.148-tegra，L4T 36.4.3，CUDA 12.6。
- 当前连接：NX Wi-Fi `wlP1p1s0=192.168.1.53/23`（ADAM_5G），可从 Windows SSH；旧有线链路 `enP8p1s0=10.42.0.2/24` 当前为 DOWN。
- NX SSH：`ssh -i C:\Users\Admin\.ssh\robomaster_nx_audit nvidia@192.168.1.53`；私钥不进入仓库。
- PX4：CUAV X7Pro 已枚举为 `/dev/ttyACM0`，稳定路径 `/dev/serial/by-id/usb-CUAV_PX4_CUAV_X7Pro_0-if00`。
- 实际相机：Orbbec Astra Pro（USB IDs `2bc5:0502`、`2bc5:0403`），当前节点仅 `/dev/video0`、`/dev/video1`；这不是 D435，也不能直接复用 D435 标定/驱动。
- 相机阻塞：NX 上尚未安装/验证 Astra Pro 的 Orbbec SDK 或 ROS 2 深度驱动；OpenNI 库存在但示例未发现可用 PrimeSense 深度设备，故深度和彩色 profile、标定、同步均未确认。
- 当前服务：`vio-watchdog.service` 会自动拉起旧版 IMU/相机链路；新 MAVLink 程序不得与旧程序同时占用 `/dev/ttyACM0`。Foxglove bridge 端口为 `8765`。
- 下一步顺序：安装/验证 Astra 驱动 → 枚举 RGB/Depth 模式 → 获取内外参与深度尺度并标定 → 发布 ROS 2/Foxglove → RGB-D VO/VIO → PX4 融合与地面测试；禁止直接用 D435 参数起飞。
