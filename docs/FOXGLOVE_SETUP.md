# Foxglove 地面可视化设置

> 日期：2026-09-13
> 适用：D430 + OpenVINS VIO + Orange Pi 5 (RK3588)
> foxglove_bridge 版本：3.4.3 (ROS2 Humble)

---

## 1. 快速连接

### 1.1 启动机载服务

在 Orange Pi 5 上：
```bash
# VIO 系统（相机 + OpenVINS + PX4 bridge）
sudo systemctl start vio.service

# Foxglove bridge + 系统监控（CPU/内存/温度）
bash /tmp/start_foxglove.sh
# 或手动：
# source /opt/ros/humble/setup.bash
# export ROS_DOMAIN_ID=42 ROS_LOCALHOST_ONLY=1
# ros2 run foxglove_bridge foxglove_bridge --ros-args -p port:=8765 -p address:=0.0.0.0 &
# python3 /home/orangepi/vio-improve/scripts/system_monitor.py &
```

### 1.2 地面电脑连接

1. 打开 Foxglove Studio（桌面端或网页版 https://studio.foxglove.dev）
2. 选择 **Open connection** → **Foxglove WebSocket**
3. 输入 URL：`ws://192.168.1.215:8765`
4. 点击 **Open**

连接成功后，左侧 **Topics** 面板会显示所有可用 topic。

---

## 2. 可用 Topic 列表

### VIO 相关
| Topic | 类型 | 说明 |
|---|---|---|
| /odomimu | nav_msgs/Odometry | VIO 里程计（~147 Hz） |
| /poseimu | geometry_msgs/PoseStamped | VIO 位姿（~15 Hz） |
| /pathimu | nav_msgs/Path | VIO 轨迹 |
| /imu | sensor_msgs/Imu | IMU 数据（~146 Hz） |
| /tf | tf2_msgs/TFMessage | 坐标变换 |
| /tf_static | tf2_msgs/TFMessage | 静态坐标变换 |
| /loop_pose | geometry_msgs/PoseStamped | 回环位姿 |
| /pathgt | nav_msgs/Path | Ground truth 路径（仿真用） |
| /posegt | geometry_msgs/PoseStamped | Ground truth 位姿 |

### 相机相关
| Topic | 类型 | 说明 |
|---|---|---|
| /camera/camera/infra1/image_rect_raw | sensor_msgs/Image | 左红外图像（848×480@30） |
| /camera/camera/infra2/image_rect_raw | sensor_msgs/Image | 右红外图像（848×480@30） |
| /camera/camera/infra1/camera_info | sensor_msgs/CameraInfo | 左相机内参 |
| /camera/camera/infra2/camera_info | sensor_msgs/CameraInfo | 右相机内参 |

### 特征与点云
| Topic | 类型 | 说明 |
|---|---|---|
| /loop_feats | sensor_msgs/PointCloud2 | 跟踪特征点 |
| /points_msckf | sensor_msgs/PointCloud2 | MSCKF 三角化点云 |
| /points_slam | sensor_msgs/PointCloud2 | SLAM 点云（如启用） |
| /points_aruco | sensor_msgs/PointCloud2 | ArUco 标记点 |
| /trackhist | visualization_msgs/MarkerArray | 跟踪历史可视化 |

### 系统监控
| Topic | 类型 | 说明 |
|---|---|---|
| /system/cpu_usage | std_msgs/Float32 | CPU 使用率（%，1 Hz） |
| /system/mem_usage | std_msgs/Float32 | 内存使用率（%，1 Hz） |
| /system/cpu_temp | std_msgs/Float32 | SoC 温度（°C，1 Hz） |

---

## 3. 推荐 Foxglove 布局

### 布局 A：VIO 监控（推荐默认）

**顶部栏（3 列）：**
1. **Image** 面板 → `/camera/camera/infra1/image_rect_raw`（左红外图）
2. **Image** 面板 → `/camera/camera/infra2/image_rect_raw`（右红外图）
3. **Plot** 面板 → `/system/cpu_usage` + `/system/mem_usage`（CPU/内存曲线）

**底部主区域：**
4. **3D** 面板 → 显示：
   - `/odomimu`（位姿，设置为 axes 或箭头）
   - `/pathimu`（轨迹线）
   - `/tf`（坐标系，显示 base_link、camera_link）
   - `/points_msckf`（点云，Size 调小如 0.02）
   - `/loop_feats`（特征点）

**右侧栏：**
5. **Plot** 面板 → `/odomimu` 的 `twist.twist.linear.x/y/z`（速度曲线）
6. **Topics** 面板 → 查看所有 topic 实时状态

### 布局 B：系统性能监控

1. **Plot** 面板（大）→ `/system/cpu_usage` + `/system/mem_usage` + `/system/cpu_temp`
2. **Plot** 面板 → `/odomimu` 的 `pose.pose.position.x/y/z`（位置曲线）
3. **Image** 面板 → 左红外图
4. **3D** 面板 → 位姿 + 轨迹

---

## 4. 3D 面板设置建议

在 3D 面板中：
- **Frame**：选择 `odom` 或 `map`（如果有）
- **Follow**：可设置跟随 `base_link`
- **Camera Sync**：开启，跟随视角
- 点云 `/points_msckf`：Point Size 设为 0.015–0.03，Color 用 height 或固定色
- 位姿 `/odomimu`：显示为 Axes（轴），Scale 0.2
- 轨迹 `/pathimu`：线宽 2，颜色区分

---

## 5. Plot 面板设置建议

### CPU/内存曲线
- 添加 series：`/system/cpu_usage`（Y 轴 0–100）
- 添加 series：`/system/mem_usage`（Y 轴 0–100）
- 可选：`/system/cpu_temp`（Y 轴 0–100）
- X 轴：时间（默认）
- 显示范围：最近 60 秒或 5 分钟

### VIO 速度曲线
- 添加 series：`/odomimu.twist.twist.linear.x`（红色）
- 添加 series：`/odomimu.twist.twist.linear.y`（绿色）
- 添加 series：`/odomimu.twist.twist.linear.z`（蓝色）
- 用于检测 VIO divergence（速度突然爆炸）

---

## 6. 故障排查

### 连接失败
1. 确认板子网络可达：`ping 192.168.1.215`
2. 确认 foxglove_bridge 运行：`ps aux | grep foxglove`
3. 确认端口监听：`ss -tlnp | grep 8765`
4. 确认防火墙：`sudo ufw status`（需允许 8765）
5. 查看日志：`tail -20 /tmp/foxglove.log`

### Topic 不显示
1. 确认 vio.service 运行：`systemctl status vio.service`
2. 确认 ROS_DOMAIN_ID 一致（都是 42）
3. 确认 ROS_LOCALHOST_ONLY=1（foxglove 和 vio 都需要）
4. 在板子上执行 `ros2 topic list` 确认 topic 存在

### 图像不显示
1. 确认相机流开启：`ros2 topic hz /camera/camera/infra1/image_rect_raw`
2. 确认 Foxglove 中 Image 面板的 topic 选择正确
3. 图像格式是 Y8（单色），Foxglove 应自动识别

### CPU/内存曲线不显示
1. 确认 system_monitor 运行：`ps aux | grep system_monitor`
2. 确认 topic 存在：`ros2 topic list | grep system`
3. 查看日志：`tail -5 /tmp/system_monitor.log`

---

## 7. 性能注意事项

- Foxglove bridge 本身 CPU 占用较低（<5%）
- 红外图像 30Hz 传输会占用一定网络带宽（约 848×480×1byte×30 ≈ 12 Mbps）
- 如果 WiFi 不稳定，可在 Foxglove 中取消订阅图像 topic，只保留 3D 和 Plot
- 系统监控 1Hz，几乎不占用资源
- Foxglove 断开不影响机载 VIO 和导航逻辑（设计原则）

---

## 8. 文件位置

| 文件 | 路径 |
|---|---|
| system_monitor 节点 | `/home/orangepi/vio-improve/scripts/system_monitor.py` |
| 启动脚本 | `/tmp/start_foxglove.sh`（后续移到仓库 scripts/） |
| foxglove 日志 | `/tmp/foxglove.log` |
| system_monitor 日志 | `/tmp/system_monitor.log` |
