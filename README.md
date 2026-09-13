# RM2027-Drone-Vio

RoboMaster 2027 无人机视觉惯性定位（VIO）系统。

**香橙派 Pi5 (RK3588) + OpenVINS (MSCKF) + RealSense D430 + PX4 v1.17**，低算力方案：视觉提供 XYZ 位置，光流提供水平速度，EKF2 完成融合。

## 系统架构

```
┌─────────────┐    USB     ┌──────────────────┐   UART(921600)  ┌─────────────┐
│ RealSense   │───────────>│   香橙派 Pi5      │<──────────────>│  PX4 v1.17  │
│ D430 (无IMU)│  图像/IMU  │  OpenVINS 里程计  │   MAVLink 桥接  │  EKF2 融合  │
└─────────────┘            └──────────────────┘                 └─────────────┘
                                 ▲                                    ▲
                           /ov_msckf/odom                     视觉位置+姿态
                             (ROS2)                         VISION_POSITION_ESTIMATE
```

- **OpenVINS (MSCKF 滤波法)**：算力开销低，适配 RK3588 低算力场景
- **飞控 IMU**：通过 USB 串口 (`/dev/ttyACM*`, 921600) 直接供 OpenVINS 使用
- **桥接节点**：pymavlink 直接发送 `VISION_POSITION_ESTIMATE`（msgid=102, v20.common 方言 9 字段含协方差，CRC=158），**不装 MAVROS**
- **EKF2 配置**：`EKF2_EV_CTRL=3`（只融合视觉 XYZ 位置，不融合视觉速度/偏航），水平速度由光流提供

## 目录结构

```
├── vio_bridge_combined.py      # 桥接主程序（IMU读取 + VIO回传 + 航向初始化）
├── vio_status.py               # SSH中文状态监控面板（命令: vio-status）
├── vio.service                 # systemd 服务单元（开机自启）
├── start_vio_systemd.sh        # 自启动脚本（flock 防多实例 + 串口自动检测）
├── start_vio.sh                # 手动启动脚本
├── start_rviz.sh               # RViz 可视化
├── build_vio.sh                # OpenVINS 编译（colcon，2线程防OOM）
├── scripts/                    # 飞控调试脚本（参数读写/消息验证/串口检查等）
├── ov_msckf/                   # 修改后的 OpenVINS 核心包（ARM64段错误修复）
└── config/
    ├── d430/                   # D430 相机配置（estimator_config.yaml 等）
    └── vio_bridge/
        └── vio_display.rviz    # RViz 显示配置
```

## 快速开始

```bash
# 1. 编译（需先安装 ROS2 Humble + RealSense SDK）
bash ~/build_vio.sh

# 2. 安装自启动服务
sudo cp vio.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable vio.service

# 3. 状态监控（SSH 登录后）
vio-status
# 面板中文显示各功能状态，可选查看 VIO/EKF 的 XYZ 实时数据
```

## 飞控参数（QGC 设置）

| 参数 | 值 | 说明 |
|---|---|---|
| `EKF2_EV_CTRL` | **3** | 视觉水平+垂直位置融合（bit0+bit1），不融合视觉速度/偏航 |
| `EKF2_HGT_REF` | 3 | 视觉高度参考 |
| `EKF2_EV_DELAY` | 50 | 视觉数据延迟补偿 (ms) |
| `SYS_HAS_GPS` | 0 | 无 GPS |
| `SYS_HAS_MAG` | 0 | 无磁力计 |

> PX4 v1.17 已废弃 `EKF2_AID_MASK`，视觉融合开关由 `EKF2_EV_CTRL` 控制。

## 关键技术点

### 消息编码（易踩坑）
- 必须用 **pymavlink 2.4.41** + `v20.common` 方言（9 字段含 21 元素协方差，完整 MAVLink2 包最大 129 字节）
- 旧 `ardupilotmega` 方言 7 字段 40 字节**无协方差，不可用**
- `VISION_POSITION_ESTIMATE` msgid=102, CRC=158

### 坐标系转换（ENU→NED）
- 位置：`x_ned = msg.y, y_ned = msg.x, z_ned = -msg.z`
- 四元数：`q_ned = q_en2ned ⊗ q_enu`，其中 `q_en2ned = (0, 0.7071, 0.7071, 0)`

### 无磁力计/无视觉偏航下的航向初始化（方案A）
EKF2 在无磁力计+无偏航融合时偏航永不对齐，水平位置融合无法启动（flags=229 卡死）。
桥接节点在 VIO 通过启动健康检查后发送 `MAV_CMD_EXTERNAL_ATTITUDE_ESTIMATE`(620)，并且只有收到 PX4 的 `COMMAND_ACK=ACCEPTED` 才认为航向初始化成功。

### VIO 健康门控
- 启动后连续 30 个有限、低协方差、原点附近的样本通过检查，才开始向 PX4 发送视觉位置。
- 持续检查 NaN/Inf、四元数、位置协方差、绝对位置和位置跳变。
- 检测到发散后立即停止发送，不再发送“冻结位置”；看门狗会重启完整 VIO 链路。
- IMU 使用 PX4 `HIGHRES_IMU.time_usec` 的采样间隔，不再给每帧写入串口到达时间。

### 融合状态位（ESTIMATOR_STATUS, PX4 v1.17）
| bit | 含义 |
|---|---|
| bit1(2) | velocity_horiz（水平速度估计有效） |
| bit3(8) | pos_horiz_rel（水平相对位置估计有效） |
| bit8(256) | const_pos_mode（恒定位置模式） |

这些是估计器解状态标志，不编码具体融合来源；不能仅凭 bit1/bit3 宣称视觉或光流融合成功。视觉融合应通过 `vehicle_visual_odometry`、EV innovation/control status 和 ULog 验证。

## 历史飞行记录

旧配置曾完成三次室外飞行，第三次（52.3m / 3分16秒 / 多次起降）ulog 解析：
- EKF 视觉位置融合标志：**976/976 条置位 (100%)**
- EKF 光流速度融合标志：**976/976 条置位 (100%)**
- 视觉位置创新比率 **0.000**（视觉测量被 EKF 完全采纳）
- 假位置(fake_pos) 仅 0.5%

> 查看 vehicle_visual_odom 曲线需在 QGC 将 `SDLOG_PROFILE` 设为 129（Bit0+Bit7 Computer Vision）。
>
> 这不是当前 D430 配置的放飞许可。每次修改相机 profile、内外参、时间戳或桥接代码后，都必须重新完成静态、手持三轴和系留测试。

## 已知限制与待办

- [ ] 当前 D430 848×480 配置重新完成手持、系留和真实飞行验证
- [ ] **免晃动初始化**：OpenVINS(MSCKF) 必须运动初始化。自动机场场景（落地插电即起飞、不晃动）需方案A（调低初始化阈值，靠起飞爬升初始化）或方案B（起降坪 Apriltag 绝对定位）
- [ ] 长时间悬停无磁力计下偏航漂移量评估
- [ ] 视觉日志（SDLOG_PROFILE=129）下的完整 Flight Review 分析

## 致谢

- [OpenVINS](https://github.com/rpng/open_vins)（GPL v3，本仓库含修改后的 ov_msckf 包）
- [MicroAir 微空 VIO 教程](https://micoair.cn/zh/docs/ai-tutorial/ai-tutorial-4-vio)（部署参考）
