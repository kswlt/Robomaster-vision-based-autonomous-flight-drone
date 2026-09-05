# ORB-SLAM3 D435 Pure Stereo VO 部署

本包 `ros2_ws/src/orb_slam3_d435_stereo` 只订阅 `/d435/infra1/image_raw` 与 `/d435/infra2/image_raw`，以近似时间同步（最大间隔 4 ms）调用 ORB-SLAM3 Stereo。它只发布位姿、路径与跟踪状态；源码中不存在 MAVLink、PX4 解锁、模式设置或执行器控制。

## 依赖与许可证

NX 已有 `/home/nvidia/fly/vio_benchmark/third_party/orb_slam3` 构建产物和 139 MiB 词典，可作为本机开发依赖。ORB-SLAM3 为 GPL-3.0-or-later；本适配包同样以 GPL-3.0-or-later 标注。不要将该目录的二进制文件或词典复制进本仓库。

此节点不使用 ROS 的 `cv_bridge`：NX 上该库依赖 OpenCV 4.5，而现有 ORB-SLAM3 依赖 OpenCV 4.11。直接包装 `mono8` 图像缓冲区可避免在同一进程加载两套 OpenCV ABI。

## 构建（NX）

```bash
source /opt/ros/humble/setup.bash
cd /home/nvidia/robomaster_d435_ros2_ws
colcon build --packages-select orb_slam3_d435_stereo \
  --cmake-args -DORB_SLAM3_DIR=/home/nvidia/fly/vio_benchmark/third_party/orb_slam3
source install/setup.bash
```

启动前必须已运行 `d435_ir_publisher`，并使用项目的工厂标定配置：

```bash
ros2 run orb_slam3_d435_stereo stereo_node --ros-args \
  -p vocab:=/home/nvidia/fly/vio_benchmark/third_party/orb_slam3/Vocabulary/ORBvoc.txt \
  -p settings:=/home/nvidia/robomaster_d435_ros2_ws/src/orb_slam3_d435_stereo/config/d435_stereo_640x480.yaml
```

地面验收首先观察 `/orb_slam3/stereo/tracking_state`、`/orb_slam3/stereo/pose` 和 `/orb_slam3/stereo/path`。只有在静态/手持实景中完成初始化、尺度和失跟恢复验证后，才可讨论后续 PX4-IMU VIO；本阶段不能起飞。
