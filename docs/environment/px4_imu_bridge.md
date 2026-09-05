# PX4 USB IMU 只读链路

采集日期：2026-09-05。NX 的 PX4 设备为 CUAV X7Pro，USB 稳定路径：

`/dev/serial/by-id/usb-CUAV_PX4_CUAV_X7Pro_0-if00 -> /dev/ttyACM0`

`nvidia` 已在 `dialout` 组。现有只读 `imu_mavlink_bridge.py --device /dev/ttyACM0 --baud 115200` 发布 `/imu/data`（`sensor_msgs/msg/Imu`），实测约 49.9–50 Hz。样本 `frame_id` 为 `fc_imu`，静止时线加速度约 `(0.063, -0.119, -9.780) m/s²`，角速度约 `(-0.00214, -0.00081, 0.00125) rad/s`。

当前消息的姿态协方差为 `-1`，线加速度和角速度协方差为全零；桥接器日志显示 `offset=None`。因此这条链路目前只能作为 PX4 IMU 可达性和频率基线，不能直接宣称已经满足飞行级 VIO 标定。

## Stereo-Inertial VIO 前置条件

还需要地面标定并记录：

- `fc_imu` 到 D435 IR1 的刚体外参（ORB-SLAM3 的 `IMU.T_b_c1`）；
- PX4 IMU 噪声、随机游走和时间偏移；
- ROS 图像时间戳与 MAVLink IMU 时间戳的统一策略；
- 静止、手持移动、遮挡和失跟恢复验收。

在这些条件完成前，项目只运行 Pure Stereo VO 或只读 IMU 监测，不切换 PX4 模式、不解锁、不发送执行器控制。
