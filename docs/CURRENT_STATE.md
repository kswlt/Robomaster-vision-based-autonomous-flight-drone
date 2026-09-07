# Current State

- 当前阶段：**VIO 启用与稳定性验证**；Astra Pro RGB-D 输入已验证，地面 RGB-D VO 冒烟通过，PX4 EKF2 视觉融合已验证，**ORB-SLAM3 紧耦合 VIO（IMU_RGBD）已启用并解决崩溃问题**。
- 状态：IN_PROGRESS（Phase B）；RGB-D 标定按用户决定跳过（用默认内参），视觉融合验证通过，VIO 稳定运行但重力对齐/方向对应待场景恢复后验证，悬停测试（第 7 步）未开始。
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

## RGB-D VO（ORB-SLAM3）— 冒烟已验证（2026-09-07）

- **新增 `rgbd_node`**（`/home/nvidia/fly/vio_benchmark/ros2_ws/src/orb_slam3_ros2/src/rgbd_node.cpp`）：message_filters 同步 `/camera/color/image_raw`(rgb8) + `/camera/depth/image_raw`(16UC1)，调 `TrackRGBD`；输出 `/orb_slam3/{pose,tracking_state,path}` + TF `map->astra`。
- **配置**：`config/astra_rgbd.yaml`——PinHole 640×480、fx=fy=570.342、cx=319.5、cy=239.5、`Camera.RGB: 1`、`RGBD.DepthMapFactor: 1000`、`Stereo.ThDepth: 40`、`Stereo.b: 0`（此 fork 的 Settings.cc 要求这三个键，缺一即 abort）。
- **冒烟结果**（静态场景，45s）：tracking_state=2 持续跟踪；位姿 ~21-25 FPS；每帧处理 ~29-32ms；1293 帧中 1 次地图重置（Local Mapping reset），无 LOST 事件；设备全程存活。
- 说明：纯 VO 冒烟（无 IMU、无 GT，按项目纪律不报 ATE/RPE）。

## RGB-D+IMU 紧耦合 VIO（ORB-SLAM3 IMU_RGBD）— 已启用（2026-09-07）

- **动机**：用户观察到 Foxglove 中里程计方向与飞机实际方向不对应，要求启用 VIO 改善重力对齐。纯 VO 的 map 系朝向任意且无外参标定；紧耦合 VIO 能利用 IMU 做重力对齐（roll/pitch），但 yaw 仍任意。
- **wrapper 改造**：`rgbd_node.cpp` 添加 `/imu/data` 订阅（RELIABLE QoS，10）、IMU 测量缓冲（deque+mutex，保留 5 秒）、`System::IMU_RGBD` 传感器类型、`TrackRGBD(im,depth,ts,vImu)` 调用、`use_imu` 参数。原纯视觉版备份为 `rgbd_node.cpp.bak_noimu`。
- **配置**：`config/astra_rgbd_imu.yaml`——基于 `astra_rgbd.yaml`，添加 IMU 噪声参数（EuRoC 默认值粗略：gyro_noise=1.7e-4, acc_noise=2e-3, gyro_walk=1.7e-5, acc_walk=3e-3, freq=200）、`IMU.fastInit=1`（跳过加速度变化>0.5 m/s² 的初始化阈值）、外参 `IMU.T_b_c1`。
- **外参**：`IMU.T_b_c1` = camera→IMU 变换（ORB-SLAM3 的 `mTcb` 定义）。PX4 转发的 IMU 为 **FLU 坐标系**（静止时 z≈-9.81，x≈0.34 bias），OpenCV 相机为 x右/y下/z前。轴置换矩阵 `[[0,0,1],[-1,0,0],[0,-1,0]]`（IMU_x=相机_z前, IMU_y=-相机_x, IMU_z=-相机_y）。**注意参数名是 `IMU.T_b_c1`（不是 `IMU.T_b_c`）**。
- **关键修复（踩坑记录）**：
  1. **QoS 不匹配**：桥发布 IMU 用 RELIABLE，wrapper 订阅用 SensorDataQoS(BEST_EFFORT) → 收不到 IMU（`not IMU meas`）。改为 `rclcpp::QoS(10)`。
  2. **IMU 时间戳 bug**：桥的 `on_imu` 原计算 `t_ros = now - offset_ns*1e9` 错误，导致 IMU 时间戳变成 PX4 boot time（几百秒），与图像 Unix 时间戳差 50 年 → VIO 的 IMU 窗口永远空。修复为直接用 `now.to_msg()`（MAVLink 传输延迟~1ms 可接受）。
  3. **IMU 时间戳超前（核心崩溃原因）**：IMU 时间戳（ROS 当前时间）比图像时间戳新约 20ms（图像采集延迟）。ORB-SLAM3 的 `PreintegrateIMU()` 提取条件为 `IMU.t < 当前帧.t - mImuPer`，IMU 超前导致第一个点就触发 else 分支（加入并 break），`mvImuFromLastFrame` 只有 1 个点 → n=0 → `Empty IMU measurements vector!!!` → 预积分失败 → `SO3::exp(omega=NaN)` abort 或 Segmentation fault。**修复：IMU 回调中时间戳减去 0.025s**，确保 IMU 时间戳略早于图像时间戳。
  4. **初始化加速度阈值**：ORB-SLAM3 `StereoInitialization()` 在 IMU 模式下要求特征点>500 + IMU 预积分非空 + 加速度变化>0.5 m/s²（除非 fastInit）。启用 `IMU.fastInit=1` 跳过。
  5. **深度流全 0**：曾出现深度图有效像素 0%（虽有 30Hz 但数据全 0），导致 `New Map created with 0 points`。重启 vision-stack 后恢复（50%+ 有效）。疑似相机预热或 USB 链路瞬时问题。
- **当前状态**：VIO 初始化成功（500+ 地图点），**不再崩溃**（修复前 1-2 秒必崩，修复后稳定运行分钟级，0 丢失）。飞控融合恢复正常（VISION_POS_ACTIVE=True）。场景差（黑暗/无纹理/深度无效）时会 LOST 并自动重置，属正常行为。
- **待验证**：① 重力对齐（roll/pitch 应接近 0）——需在有纹理场景下测量；② 里程计方向与飞机实际方向对应——VIO 只能对齐 roll/pitch，yaw 仍任意，需飞控 EKF2 融合后统一；③ 长时稳定性（纯 VO 曾 ~44min NaN abort，VIO 需复测）。
- **IMU 数据源**：`px4_fusion_bridge.py` 转发 PX4 HIGHRES_IMU → `/imu/data`，~193 Hz，FLU 坐标系，RELIABLE QoS。

## PX4 视觉融合（第 6 步）— 已验证（2026-09-07）

- **桥**：`px4_fusion_bridge.py`（NX `/home/nvidia/fly/vio_benchmark/scripts/run/px4_fusion_bridge.py`，Windows 母本 `C:\Users\Admin\DoubaoWork\chats\2026-09-06\new-chat\`）：订阅 `/orb_slam3/pose` → ENU→NED（`Q_EN2NED` 四元数左乘）→ MAVLink `ODOMETRY`(LOCAL_NED, 位置协方差 0.01 m², quality 省略) 注入；同时转发 HIGHRES_IMU 250Hz→`/imu/data`；ESTIMATOR_STATUS 5Hz 监测融合标志。
- **固件参数体系（关键发现）**：该 PX4 为 **2025+ 新版 EKF2 参数体系**——有 `EKF2_EV_CTRL`（位0 水平位置 / 位1 垂直位置 / 位2 速度 / 位3 偏航），**无**旧版 `EKF2_AID_MASK`/`SYS_MC_EST_GROUP`/`MAV_ODOM`。实测 **`EKF2_EV_CTRL=15`（int，全开）**——疑似 D435 时代 AID_MASK 视觉位被固件升级自动迁移；`EKF2_EV_POS_{X,Y,Z}=0`（相机外参未标定）、`EKF2_EVP_GATE=5`、`EKF2_EVV_GATE=3`、`EKF2_EVP_NOISE=EVV_NOISE=0.1`、`COM_ARM_EKF_{POS,VEL}=0.5`。**无需改任何参数即可融合。**
- **pymavlink 兼容补丁**（已固化进桥）：① int32 参数经 `PARAM_VALUE.param_value` 以 **float 位模式**传输（`EKF2_EV_CTRL` 读为 2.1e-44 = int 15；`MAV_TYPE`=2.8e-45=int 2）——读取整型参数需按 `param_type` 解位模式；② 该方言 `estimator_status` 为 **MAVLink1 旧版**（仅 10 字段，flags 最高 bit10，**无 vision 专用位、无 innovation_metric**）→ 融合判据用 `const_pos`(bit7)/`pos_horiz_abs`(bit4)/`pred_pos_abs`(bit9) 组合；③ PX4 新固件偶发发送 pymavlink 无法注册的消息导致 `add_message` 崩溃（间歇）→ monkey-patch 跳过坏消息；④ **PX4 不主动发 TIMESYNC**，须主动 `timesync_send` 建立 offset（offset = PX4时钟 − 本地时钟，注入时间戳 = 本地 + offset）；⑤ **pymavlink 方言坑（重启后首次暴露）**：`mavutil` 模块 import 时执行 `set_dialect(os.environ['MAVLINK_DIALECT'])`，且**默认走 v10 协议**——**v10 common 方言没有 `odometry_send`（ODOMETRY 仅 v20 有）**，导致服务重启后桥在 `on_pose` 处 `AttributeError` 崩溃循环（重启前手动环境偶然满足条件）。修复：桥在 `import mavutil` **之前**设置 `MAVLINK_DIALECT=common` + `MAVLINK20=1` 并显式 `mavutil.set_dialect("common")`，强制 v20 common。
- **注入验证结果**（完整链路 60 s，静态场景）：EKF 从 `const_pos_mode`(flags=0xe5) **切换到视觉绝对位置融合**（flags=0x37f：`pos_horiz_abs=1`、`const_pos=0`、`vel_h=1`，持续 60 s）；**创新比率 pos_h=0.01~0.02、pos_v≈0.01、vel≈0.00（门限 1.0）**——视觉观测被 EKF 平滑接受、无拒绝无震荡。桥：IMU ~195 Hz、ODOMETRY ~23 Hz；VO：1881 帧 0 LOST；相机存活。
- **已知边界（飞行前注意）**：相机外参 `EKF2_EV_POS_*=0`（未标定，用户决定跳过）；ORB-SLAM3 地图系朝向任意（无重力对齐，yaw 相对视觉帧）；位置为**静态验证**（无人机未动），动态下创新需复测；`EKF2_EV_CTRL` 含 bit3(yaw) 时航向相对外部视觉系。

## 硬件注意事项（重要）

- Astra Pro 当前仍挂在**两级无源 USB Hub 链**（0608→0610）上，电气余量不足：曾发生深度流启动后整链掉线（dmesg：`Cannot enable`、`buffer overrun`、`disabled by hub (EMI?)`），需物理重插才恢复。
- 重插后深度+彩色双流已稳定运行；**生产/悬停测试前建议直连 NX USB 口或改用供电 Hub**。
- RGB 的 uvcvideo 驱动曾在测试中解绑（`unbind`），重启后会自动重新绑定；libuvc 走 `/dev/astra_pro_rgb` 不受影响。

## PX4 参数快照（2026-09-07 只读检查）

- 机型：`SYS_AUTOSTART=4001`（Generic Quadcopter，X 四旋翼）、`MAV_TYPE=2`。⚠ 需用户确认与实机机架/电机映射一致。
- EKF：`EKF2_EV_CTRL=15`（视觉全开）、`EKF2_GPS_CTRL=0`（GPS 融合关，室内正确）、`EKF2_HGT_REF=0`（高度=气压计，室内漂移风险）、`EKF2_EVP_NOISE=EVV_NOISE=EVA_NOISE=0.1`、gate 5/3、`EV_POS_*=0`、`EV_QMIN=0`、`EV_DELAY=0`、`EV_NOISE_MD=0`。
- 解锁：`COM_ARM_EKF_POS=0.5`、`VEL=0.5`、`HGT=1`、`COM_ARM_IMU_ACC=0.7`、`COM_ARM_AUTH_REQ=0`。
- RC：`COM_RC_IN_MODE=3`、`RC_CHAN_CNT=18`、映射 ROLL=1/PITCH=2/THROTTLE=3/YAW=4/ARM=6/KILL=5、`MODE_SW=0`、`OFFB_SW=0`；`COM_RC_LOSS_T=0.5s`、`NAV_RCL_ACT=3`（RC 丢失→Land）、`COM_OF_LOSS_T=1s`。
- 电池：6S（`BAT1_N_CELLS=6`、4.2/3.6V、24 A/V）；`COM_LOW_BAT_ACT=0`（**低压无动作，需确认**）。
- ⚠ 安全：`CBRK_FLIGHTTERM=121212`（**飞行终止被禁用**，需用户确认是否故意/恢复）、`CBRK_SUPPLY_CHK=0`、`CBRK_VTOLARMING=0`。
- 控制：`MPC_THR_HOVER=0.5`（默认，实机需校准）、`MPC_XY_CRUISE=5`、`MPC_Z_VEL_MAX_UP=3`、`MPC_LAND_SPEED=0.7`、`NAV_ACC_RAD=2`、`COM_DISARM_LAND=2`。
- 串口：`SER_TEL1_BAUD=115200`、`SER_TEL2_BAUD=57600`、`GPS_1_CONFIG=201`、`MAV_0_CONFIG=101`（USB）、`MAV_1_CONFIG=102`。
- 无旧参数：`SYS_MC_EST_GROUP`/`SYS_USE_IO`/`COM_ARM_ARSPD_EN` 等不存在（新版 EKF2 体系佐证）。

## 当前服务（2026-09-07 自启动化完成）

- **`vision-stack.service`**（Restart=always）：foxglove_bridge(`:8765`) + Astra Pro 相机（640×480，供 VO）+ **`foxglove_image_resizer.py`**（纯 numpy 缩放 640×480→320×240，发布 `/foxglove/{color,depth}/image_raw`，仅给 Foxglove 降带宽；相机/VO 仍用原始高分辨率）。foxglove_bridge 白名单只暴露 `/foxglove/.*`+`/orb_slam3/.*`+`/tf`+`/tf_static`+`/imu/.*`，不传输原始 640×480 图像。
  - ⚠ **foxglove_bridge 的 `topic_whitelist` 是正则表达式，不是 glob**——`/camera/**` 匹配不到实际话题，须写 `/camera/.*`。
- **`orb-slam3.service`**（Restart=on-failure, RestartSec=8, After=vision-stack）：**RGB-D+IMU 紧耦合 VIO**（`use_imu:=true`，config `astra_rgbd_imu.yaml`，传感器类型 `IMU_RGBD`）。启动脚本 `start_orb_slam3.sh`。纯 VO 模式曾连续运行 ~8 万帧（~44 min）后 Sophus `SO3::exp failed (omega=NaN)` abort——服务自动重启兜底；VIO 模式已解决初始化后 1-2 秒崩溃问题（IMU 时间戳回调 25ms），长时稳定性待复测。
- **`px4-fusion-bridge.service`**（Restart=on-failure）：PX4 融合注入（ODOMETRY + IMU 转发）。wrapper 位于 `${ROOT}/scripts/run/start_{vision_stack,orb_slam3,px4_bridge_service}.sh`。
- **`vio-watchdog.service` 已 disable**（防重启后旧 IMU 桥抢占 `/dev/ttyACM0`）；其托管内容（旧相机/IMU 链路）不再自启动。
- **电池供电重启验证（2026-09-07）**：切换飞行电池供电并重启后——WiFi `ADAM_5G` 已改为**静态 IP 192.168.1.53/23**（autoconnect=yes，重启自动回连）；三个服务全部自启恢复；修复 ⑤ 方言坑后桥稳定：IMU ~193 Hz、ODOMETRY 93 Hz、`VISION_POS_ACTIVE=True`（flags=0x37f，创新 0.00~0.01）。VO ~23.7 FPS。

## 下一步（按 PROJECT_PROMPT_ZH 顺序）

1. **标定（第 3 步）**：用户决定跳过棋盘格标定，直接使用驱动默认内参（fx=fy=570.342，深度毫米×0.001→米）。已知限制：彩色/深度视为已对齐（未做外参标定），VO 冒烟可接受，若轨迹发散再补标定。
2. **Foxglove 接入（第 4 步）**：桥 `:8765` 已确认监听运行；图像话题为低分辨率 `/foxglove/color/image_raw`、`/foxglove/depth/image_raw`（320×240），VO 话题 `/orb_slam3/pose`、`/orb_slam3/path`，TF `map→astra`；3D 面板参考系选 `map`，勾选 `/orb_slam3/path` 显示轨迹。
3. **地面 RGB-D VO（第 5 步）**：**已完成冒烟**——ORB-SLAM3 RGB-D（`rgbd_node`）640×480 双流，~20-25 FPS 输出位姿，每帧处理 ~30ms，1293 帧仅 1 次地图重置、无丢失事件（纯 VO smoke，无 IMU/GT）。
4. **VIO（第 5 步扩展）**：**已启用并解决崩溃**——ORB-SLAM3 IMU_RGBD 紧耦合 VIO，PX4 IMU 转发，外参 FLU→OpenCV 轴置换，IMU 时间戳回调 25ms 解决 `Empty IMU vector` 崩溃。初始化成功（500+ 点），稳定运行不崩溃。**待验证**：重力对齐（roll/pitch≈0）、方向对应、长时稳定性。
5. **PX4 融合（第 6 步）**：**已完成验证**——`px4_fusion_bridge.py` ODOMETRY 注入（~23Hz），EKF 退出 const_pos 进入视觉绝对位置融合，创新比率 0.01-0.02（≪1），60s 稳定。**自启动已完成**（三个 systemd 服务，见"当前服务"）。
6. **悬停测试（第 7 步）**：**尚未具备条件**。前置事项：① 用户用 QGC 确认/配置飞控飞行参数（机型 SYS_AUTOSTART、RC 校准与模式映射、解锁检查、失效保护、EKF 位置源）——NX 侧未改任何飞控飞行参数；② 动态移动下复测融合创新（静态已验证）；③ VIO 重力对齐和方向对应验证；④ VO/VIO 长时稳定性复测；⑤ 拆桨 + 人工授权；⑥ 确认 EKF2_EV_POS_* 外参 0 值可接受。
