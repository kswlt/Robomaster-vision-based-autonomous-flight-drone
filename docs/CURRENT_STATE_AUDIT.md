# CURRENT STATE AUDIT — d430 VIO 系统完整审计

> 审计日期：2026-09-13
> 审计对象：GitHub `kswlt/Robomaster-vision-based-autonomous-flight-drone` @ `d430`（c64aadd）+ 板子 orangepi5（192.168.1.215）实际运行态
> 方法：以代码 + 真实运行结果为准，不信任 README/docs 描述
> 历史说明：本文记录修复前状态，已由 `RUNTIME_SAFETY_REPAIR.md` 取代，不可作为当前运行配置说明。

---

## 1. 当前架构（代码确认）

```
RealSense D430 (infra1+infra2, 无RGB无IMU)
        │  ROS2 topics
        ▼
OpenVINS ov_msckf (滤波法 MSCKF, 3处源码补丁)
  输入: /imu + /camera/camera/infra{1,2}/image_rect_raw
  输出: /odomimu, /trackhist, /pathimu, /poseimu, /tf
        │
        ▼
vio_bridge_combined.py (运行版: ~/vio_ws/vio_bridge/, 20557B)
  IMU读取线程: PX4 MAVLink → /imu (NED→ENU, 150Hz实测)
  VIO回传线程: /odomimu → VISION_POSITION_ESTIMATE (ENU→NED, v20 96B)
  含: 串口自动检测 + 10次重连 + 异常≥15自动reconnect + VIO健康门控(发散保护) + 605航向对齐
        │  MAVLink USB (/dev/ttyACM0, 921600)
        ▼
PX4 飞控 v1.17 (EKF2: EV_CTRL=3 视觉水平+垂直位置, 不用视觉偏航)
```

systemd 启动顺序（vio.service）：
1. `start_vio_systemd.sh`（flock 防多实例）
2. ros2 launch realsense2_camera（**参数名错误，见问题#3**）
3. vio_bridge_combined.py（串口自动检测）
4. ov_msckf run_subscribe_msckf（前台，退出则 systemd 重启）

看门狗 watchdog_camera.service：10s 检测 camera.log 错误 → 重启 vio.service，冷却 180s。

---

## 2. Topics / Frames / Rates（实测 2026-09-13）

| Topic | Type | 实测状态 |
|---|---|---|
| /camera/camera/infra1/image_rect_raw | sensor_msgs/Image | **Publisher count = 0（相机流未运行！）** |
| /camera/camera/infra2/image_rect_raw | sensor_msgs/Image | **Publisher count = 0（相机流未运行！）** |
| /imu | sensor_msgs/Imu | ✅ 150.66 Hz（请求 200Hz，实测 150Hz 为飞控上限） |
| /odomimu | nav_msgs/Odometry | ❌ 无发布（VIO init=0，无图像输入） |
| /tf | tf2_msgs/TFMessage | OpenVINS 发布中（有 publisher） |
| /trackhist /pathimu /poseimu /points_msckf 等 | — | OpenVINS 调试话题 |

**关键**：infra1/infra2 无 publisher → OpenVINS 无图像 → `[odom-dbg] init=0` 持续 → odomimu 不发布 → 视觉链路实际未工作。

---

## 3. 关键配置（运行时 ~/vio_ws vs 仓库 d430）

### 3.1 estimator_config.yaml（⚠️ 仓库与运行时不一致）

| 参数 | 运行时 (~/vio_ws) | 仓库 (d430) | 判定 |
|---|---|---|---|
| calib_cam_extrinsics | **false** | true | 运行时=稳定版（文档一致） |
| calib_cam_intrinsics | **false** | true | 运行时=稳定版（文档一致） |
| calib_cam_timeoffset | true | true | 一致 |
| zupt_chi2_multipler | **1.0** | 0 | 运行时=稳定版（文档一致） |
| zupt_max_disparity | **0.2** | 0.5 | 运行时=稳定版（文档一致） |
| track_frequency | 21.0 | 21.0 | 一致 |

**结论**：仓库里的 estimator_config.yaml 是初始默认值（未应用稳定参数），运行时才是稳定版。**仓库需同步运行时版本**。

### 3.2 kalibr_imucam_chain.yaml（⚠️ 仓库与运行时不一致）

| 项 | 运行时 (~/vio_ws) | 仓库 (d430) | 判定 |
|---|---|---|---|
| T_imu_cam cam0 | ENU旋转[0,0,1;-1,0,0;0,-1,0] + 平移[0.08,0,0] | **单位阵（无旋转无平移）** | 运行时=ENU版（文档一致） |
| T_imu_cam cam1 | 同旋转 + 平移[0.08,-0.05,0] | [0,-0.05,0] 无旋转 | 运行时=ENU版（文档一致） |
| intrinsics | [318.66,318.66,319.38,240.207]（640应急） | [422.216,...]（848） | 运行时=640应急（相机当前640@15） |
| resolution | [640,480] | [848,480] | 运行时=640应急 |

**结论**：运行时外参 = ENU 版（与文档 7.9 一致）；仓库外参 = 错误单位阵。**仓库需同步 ENU 外参**。分辨率差异 = 640 应急 vs 848 目标，恢复 848 后切回。

### 3.3 kalibr_imu_chain.yaml — 完全一致（IDENTICAL）

---

## 4. docs/code mismatch 清单（关键发现）

### 4.1 vio_bridge_combined.py 存在两个版本
- **运行版**：`~/vio_ws/vio_bridge/vio_bridge_combined.py`（20557B, md5=62e0cb8e）— 含串口检测/重连/门控/605 ✅
- **仓库版**：`vio_bridge_combined.py`（10958B, md5=8228645a）— **旧版**，无 605、无门控、无重连 ❌
- **结论**：仓库与 home 根目录的是旧版；实际运行的是 ~/vio_ws 版。**仓库必须同步运行版**。

### 4.2 MAV_CMD_EXTERNAL_ATTITUDE_ESTIMATE(605) 航向对齐
- 运行版 ✅ 存在（一次性 yaw_reset_sent，param3=heading deg）
- 仓库版 ❌ 不存在
- 结论：同 4.1，同步运行版即修复。

### 4.3 VIO 健康门控 + 自动重连
- 运行版 ✅：发散检测（速度>5m/s 连续5帧 或 位置>150m）→ 发最后可信值+大协方差(BAD_COV=1000)；恢复（速度<1m/s 连续10帧）→ 重新605对齐。日志带 `[正常]/[发散保护]` 标签。
- 仓库版 ❌ 无。
- 结论：同 4.1。

### 4.4 ESTIMATOR_STATUS flags 检查（已核实 MAVLink 定义）
MAVLink ESTIMATOR_STATUS_FLAGS 定义（common.xml）：
```
1   ESTIMATOR_ATTITUDE
2   ESTIMATOR_VELOCITY_HORIZ
4   ESTIMATOR_VELOCITY_VERT
8   ESTIMATOR_POS_HORIZ_REL
16  ESTIMATOR_POS_HORIZ_ABS
32  ESTIMATOR_POS_VERT_ABS
64  ESTIMATOR_POS_VERT_AGL
128 ESTIMATOR_POS_VERT_TOTAL
256 ESTIMATOR_CONST_POS_MODE
```
- **运行版** ✅：`flags & 8`（POS_HORIZ_REL=视觉水平位置）、`flags & 2`（VELOCITY_HORIZ=光流速度）— **正确**
- **仓库版** ❌：`flags & 16`（注释为POS_HORIZ_REL，实际是POS_HORIZ_ABS）、`flags & 4`（注释为VELOCITY_HORIZ，实际是VELOCITY_VERT）— **注释与含义错误**
- flags=239（实测）= 0b11101111：ATTITUDE+VEL_HORIZ+VEL_VERT+POS_HORIZ_REL+POS_HORIZ_ABS+POS_VERT_ABS+POS_VERT_AGL+POS_VERT_TOTAL → 视觉水平位置已置位；但 posH=nan（ratio 无效，因 VIO 未供数据）
- 结论：运行版正确；仓库版需同步。

### 4.5 硬件型号确认
- lsusb: `8086:0ad1` = **D430 模组**（无 RGB、无 IMU）
- camera.log: Device Name "RealSense D400", Product ID 0x0AD1, FW 5.17.3.10, USB type 3.2 (SuperSpeed)
- 仓库 d430 旧内容里的 d435/orb_slam3 文件为历史遗留，与本硬件无关（已在上次上传中移除）

---

## 5. 发现的问题（按优先级）

| # | 问题 | 严重度 | 证据 | 处理 |
|---|---|---|---|---|
| 1 | **相机流未运行**：`Error starting device: hwmon command 0x2c failed (-9)` = REC/硬件错误；infra topic Publisher count=0 | 🔴 阻塞 | camera.log + topic info | Stage 1：硬件处理（换线/换口/供电）+ 验证 |
| 2 | **launch 参数名错误**：`infra_fps/infra_width/infra_height` 不被 realsense2_camera 支持（警告已证实），848@30 请求从未生效 | 🔴 高 | camera.log Warning + rs_launch.py 参数表 | 改为 `depth_module.infra_profile:=848x480x30` |
| 3 | **仓库代码过期**：vio_bridge_combined.py（10958B）缺 605/门控/重连；运行版（20557B）在 ~/vio_ws | 🟠 高 | md5 对比 + 源码 | 同步运行版到仓库 |
| 4 | **仓库配置过期**：estimator_config.yaml（calib=true/chi2=0/disparity=0.5）、kalibr_imucam_chain.yaml（单位阵外参）≠ 运行时稳定版 | 🟠 高 | diff 对比 | 同步运行时稳定参数 + ENU 外参 |
| 5 | ESTIMATOR_STATUS flags 注释错误（仓库版 &4/&16） | 🟡 中 | 源码 | 随 #3 同步修复 |
| 6 | 历史 USB2 连接记录（Device USB type 2.1, PID 0x0AD6, serial ffffffff）→ 曾插劣化端口 | 🟡 中 | camera.log 12/09 | Stage 1 检查 USB 端口 |

---

## 6. 建议修改顺序

1. **Stage 1 相机恢复**（硬件 + launch 参数修复 `depth_module.infra_profile`）
2. 同步仓库：运行版 bridge + 稳定 config（ENU 外参、chi2=1.0、disparity=0.2、标定关闭）
3. 恢复 848@30 后验证 VIO baseline（Stage 1.5）
4. 开启 Depth（Stage 2）→ depth mapper（Stage 3）→ Foxglove（Stage 4）→ A*（Stage 5）→ Goal（Stage 6）→ Follower（Stage 7）→ Safety（Stage 8）→ Monitor（Stage 9）

---

## 7. 版本确认

| 组件 | 版本 |
|---|---|
| 操作系统 | Ubuntu 22.04 (Orange Pi OS 1.2.4, XFCE) |
| ROS2 | Humble |
| librealsense2 | 2.58.3-1jammy |
| realsense2_camera | /opt/ros/humble（ros-humble 包） |
| OpenVINS | 2.7.0（master，3处补丁） |
| pymavlink | 2.4.41 |
| 相机 FW | 5.17.3.10，PID 0x0AD1 |
| 飞控 | PX4 v1.17（USB cdc_acm, 12M, /dev/ttyACM0） |

---

*审计完成，下一步：Stage 1 恢复 D430 848×480@30。*
