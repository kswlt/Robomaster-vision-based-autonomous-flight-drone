# 香橙派 Pi5 + PX4 + D430 VIO 定位系统 — 技术方案汇总（交接版）

> 文档日期：2026-09-09（v2.2 交接更新）
> 状态：
>
> **VIO 全链路打通，但当前相机硬件受限 640@15，飞行不可用**
>
> —— 接手方首要任务：恢复 848@30



***

## 一、系统概述

### 1.1 项目目标

在香橙派 Pi5 上部署轻量化 VIO（视觉惯性里程计）系统，配合 PX4 飞控和 Intel RealSense D430 相机，实现无人机无 GPS 环境下的视觉定位，面向机场自动起降场景（插电即用、不晃动初始化、无显示器无网络）。

### 1.2 设计原则



* **低算力优先**：滤波法 VIO（OpenVINS/MSCKF）

* **无 IMU 相机**：D430 无内置 IMU，使用飞控 IMU 经 MAVLink 桥接

* **直接 MAVLink 桥接**：不依赖 MAVROS

* **开机自启**：systemd 服务

* **机场场景**：静止即初始化并发布、不晃动、自动起降



***

## 二、硬件配置



| 设备     | 型号                   | 关键参数                       | 连接方式             |
| ------ | -------------------- | -------------------------- | ---------------- |
| 机载电脑   | 香橙派 Pi5              | RK3588, Ubuntu 22.04       | —                |
| 飞控     | PX4 v1.17            | USB → /dev/ttyACM0/1（自动检测） | USB              |
| 深度相机   | Intel RealSense D430 | 双目红外，无 IMU                 | USB3.0           |
| 飞控 IMU | 飞控内置                 | 实测**150Hz**（请求 200Hz）      | MAVLink over USB |

### ⚠️ 硬件注意事项（当前卡脖子点）



* **D430 当前处于硬件 REC error 状态：只能输出 640×480@15fps**（launch 参数 848@30 被硬件忽略）

* **640@15 下飞行 VIO 必然发散**（见 7.13），**恢复 848@30 是接手方第一任务**

* 恢复方法：**换 USB 线 / 换 USB 口 / 改善供电**（REC error 是硬件级错误，软件无法绕过）

* 恢复判定：`grep 'Open profile' /tmp/camera.log` 显示 **Width: 848, Height: 480, FPS: 30**

* 恢复后执行第十节配置切换命令（内参 /resolution 切回 848）



***

## 三、软件架构



```
┌─────────────────────────────────────────┐

│              RViz2 可视化                 │

└──────────────┬──────────────────────────┘

&#x20;              │ ROS2话题

┌──────────────▼──────────────────────────┐

│            OpenVINS (ov\_msckf)           │

│  输入: /imu + /camera/camera/infra\*      │

│  输出: /odomimu, /trackhist, /pathimu    │

└──────────────┬──────────────────────────┘

&#x20;              │ ROS2话题

┌──────────────▼──────────────────────────┐

│       vio\_bridge\_combined.py             │

│  IMU读取线程: 飞控MAVLink → /imu          │

│  VIO回传线程: /odomimu → 飞控MAVLink      │

│  含: 自动重连 + VIO健康门控 + 605航向对齐  │

└──────────────┬──────────────────────────┘

&#x20;              │ MAVLink (USB串口)

┌──────────────▼──────────────────────────┐

│              PX4 飞控 v1.17              │

│     EKF2融合视觉XYZ位置 + 光流速度        │

│     （不用视觉偏航，EV\_CTRL=3）           │

└─────────────────────────────────────────┘
```

### 核心软件版本



| 软件            | 版本                       | 说明           |
| ------------- | ------------------------ | ------------ |
| 操作系统          | Ubuntu 22.04 (XFCE)      | 测试桌面版        |
| ROS2          | Humble ros-base          | 精简版          |
| RealSense SDK | 2.58.3 + Wrapper 4.5.x   |              |
| OpenVINS      | master 分支（**已修改 3 处源码**） | 7.2/7.8      |
| pymavlink     | 2.4.41                   | 2.4.49 有 bug |



***

## 四、已完成功能清单

### 4.1 系统 / 驱动层



* [x] Ubuntu 22.04、SSH、网络（Windows ICS 192.168.137.210）

* [x] systemd 自启：vio.service + watchdog\_camera.service + USB 防挂起

* [x] RealSense D430 双目红外流、飞控串口自动检测

### 4.2 VIO 核心



* [x] OpenVINS 编译（ARM64 段错误修复）

* [x] **odomimu 不发布根因修复**（ZUPT 补丁 + Propagator 补丁，静止即发布）

* [x] **外参标定**（ENU 版旋转 + 8cm 平移）

* [x] **ZUPT 防误触发修复**（chi2 检验 + 视差阈值 0.2）

* [x] IMU 桥接（NED→ENU）、VIO 回传（ENU→NED, VISION v20 96 字节）

* [x] VIO 健康门控（发散保护 + 自动恢复）

### 4.3 系统集成



* [x] 开机自启、RViz、PX4 EKF2 参数（EV\_CTRL=3，用户 QGC 维护）

* [x] 桥接自动重连（pymavlink 崩溃防护）

* [x] 看门狗冷却 180 秒

### 4.4 运行指标（当前 640@15 实测）



| 指标        | 当前值                | 说明              |
| --------- | ------------------ | --------------- |
| IMU 频率    | 150Hz              | 请求 200Hz        |
| VIO 输出    | \~100Hz            | /odomimu 静止也发布  |
| 特征点       | 80-102 个           | 视环境             |
| 静止稳定性     | 0.001m/s, 0 发散     | ✅               |
| **飞行稳定性** | **发散**             | ❌ 640@15 不适用于飞行 |
| CPU / 内存  | \~25-30% / \~330MB |                 |



***

## 五、关键配置参数

### 5.1 PX4 飞控参数（QGC 维护，**必须人工改，禁止自动改**）



| 参数              | 值     | 说明                      |
| --------------- | ----- | ----------------------- |
| EKF2\_EV\_CTRL  | **3** | 视觉水平 + 垂直位置（**不要视觉偏航**） |
| EKF2\_HGT\_REF  | 3     | 视觉高度                    |
| EKF2\_EV\_DELAY | 50    | 视觉延迟 50ms               |
| SYS\_HAS\_GPS   | 0     | 无 GPS                   |
| SYS\_HAS\_MAG   | 0     | 无磁力计                    |

> **铁律**
>
> ：EV_CTRL=11（含视觉偏航）→位置永不融合（flags=229 卡死）。本系统永远用 = 3。

### 5.2 ROS2 环境变量（\~/.bashrc）



```
export ROS\_DOMAIN\_ID=42

export ROS\_LOCALHOST\_ONLY=1
```

### 5.3 OpenVINS 配置（\~/vio\_ws/src/open\_vins/config/d430/）

**estimator\_config.yaml 关键参数（当前）：**



| 参数                         | 当前值       | 说明                                  |
| -------------------------- | --------- | ----------------------------------- |
| num\_pts                   | 100       | 最大特征数                               |
| num\_opencv\_threads       | 1         | 低算力                                 |
| try\_zupt                  | true      | 零速更新                                |
| **zupt\_chi2\_multipler**  | **1.0**   | **启用 IMU 一致性检验**（防晃动误清零，原 0 = 只看视差） |
| **zupt\_max\_disparity**   | **0.2**   | **严格静止判定**（原 0.5 太宽松）               |
| zupt\_max\_velocity        | 0.1       | 速度上限                                |
| **calib\_cam\_extrinsics** | **false** | **关闭外参在线标定**（用标定好的 ENU 外参，防开机晃动带偏）  |
| **calib\_cam\_intrinsics** | **false** | **关闭内参在线标定**（用出厂 / 缩放内参）            |
| calib\_cam\_timeoffset     | true      | 保留（时间偏移必须在线，已收敛 0.00448s）           |

**kalibr\_imucam\_chain.yaml（外参，ENU 版，勿改）：**



```
cam0: \[0,0,1, 0.08]   ← 旋转: 相机前→机头前(ENU) + 平移: 前移8cm

&#x20;     \[-1,0,0, 0.0]

&#x20;     \[0,-1,0, 0.0]

cam1: 同旋转 + 平移 \[0.08, -0.05, 0]（右相机基线5cm）
```

> **IMPORTANT**
>
> ：OpenVINS 内部 IMU 系为 ENU（X 前 Y 左 Z 上）。用 NED 版旋转（
>
> `[0,0,1;1,0,0;0,1,0]`
>
> ）→初始化后速度飙 53m/s 发散。ENU 版→静止 0.001m/s。

**kalibr\_imucam\_chain.yaml 分辨率 / 内参（当前 640 应急）：**



* 分辨率：`[640, 480]`、内参：`[318.66, 318.66, 319.38, 240.207]`

* 848 版：`[848, 480]`、`[422.216, 422.216, 423.231, 240.207]`（恢复 848 后切回）

**kalibr\_imu\_chain.yaml：** 话题`/imu`，update\_rate 200（实测 150），噪声参数用 kalibr 默认值（acc 2e-3, gyro 1.7e-4）



***

## 六、文件结构



```
/home/orangepi/

├── vio\_ws/

│   ├── src/open\_vins/

│   │   ├── ov\_msckf/src/ros/ROS2Visualizer.cpp/.h   # ARM64段错误修复

│   │   ├── ov\_msckf/src/state/Propagator.cpp        # 补丁: 50ms窗口

│   │   ├── ov\_msckf/src/core/VioManager.cpp         # 补丁: ZUPT也更新timelastupdate

│   │   └── config/d430/                             # estimator\_config.yaml + kalibr\_\*.yaml

│   ├── install/

│   └── vio\_bridge/vio\_bridge\_combined.py            # 桥接(重连+门控+605+串口检测)

├── start\_vio\_systemd.sh             # systemd启动(含realsense launch 848@30参数)

├── watchdog\_camera.sh               # 看门狗(冷却180s)

├── patch\_propagator.py / patch\_zupt\_timelast.py     # 补丁脚本

├── vio\_status.py                    # SSH中文面板(vio-status)

├── grab\_frames.py / grab\_frames2.py # 抓帧诊断

└── /swapfile

/etc/systemd/system/vio.service

/etc/systemd/system/watchdog\_camera.service

/etc/udev/rules.d/99-usb-autosuspend.rules
```

### 日志（/tmp，断电丢失）



* `/tmp/camera.log`（覆盖式）、`/tmp/vio.log`、`/tmp/vio_bridge.log`、`/tmp/watchdog.log`、`/tmp/vio_restart.log`

* 关键检索：`grep '已发送VISION' /tmp/vio_bridge.log | tail`（\[正常]/\[发散保护] 标签）、`grep 'EKF状态' /tmp/vio_bridge.log | tail`、`grep -E 'ZUPT' /tmp/vio.log | tail`

### SSH 状态面板

`vio-status`：中文 8 项状态 + 交互 XYZ/RPY。



***

## 七、关键技术决策与踩坑记录

### 7.1-7.6 早期决策（已定稿）

VIO 选型 OpenVINS 滤波法；ARM64 段错误修复（image\_transport→rclcpp::Publisher，`if(true)`无条件发布勿改回）；串口单进程；pymavlink 2.4.41；ROS 域统一 42；IMU 频率靠桥接 SET\_MESSAGE\_INTERVAL 请求。

### 7.7 坐标转换（勿改）



* IMU：飞控 NED → ROS ENU（y 取反、z 取反）

* VIO 回传：ENU → NED（`x_ned=msg.y, y_ned=msg.x, z_ned=-msg.z`）

* 消息：VISION\_POSITION\_ESTIMATE msgid=102，**v20.common 9 字段 96 字节，必须含协方差 + reset\_counter**（旧 ardupilotmega 7 字段 40 字节不可用）

### 7.8 ★ odomimu 不发布根因与修复（已解决）



* 根因 1：Propagator 15ms 窗口 < 2 条 IMU → 发布 return → **窗口扩展 50ms 补丁**

* 根因 2（最终）：**ZUPT 静止时每次成功→提前 return→timelastupdate 永不更新→odomimu 永不发** → **VioManager.cpp 补丁**（ZUPT 成功分支加`timelastupdate = message.timestamp;`）

* 效果：**静止也持续发布 odomimu**，机场插电即用

* 验证：`grep odom-dbg /tmp/vio.log | tail` → `init=1`；`ros2 topic hz /odomimu`

### 7.9 ★ 外参标定（ENU 版，已定稿）

OpenVINS IMU 系 = ENU（X 前 Y 左 Z 上）。相机朝前安装：T\_imu\_cam 旋转 =`[0,0,1;-1,0,0;0,-1,0]`+ 平移前移 0.08m。NED 版会 53m/s 爆炸（已验证勿试）。ENU 版静态 0.001m/s。

### 7.10 ★ 相机分辨率不匹配→0 特征（已解决）

D430 REC error→强制 640@15→配置还是 848 内参→0 特征。**配置同步 640 后恢复**（特征 73-102 个）。

### 7.11 ★ 桥接自动重连（已解决）

pymavlink 偶发 TypeError 崩溃→wait\_heartbeat 重试 10 次 + 异常计数≥15 自动 reconnect + 串口自动检测。

### 7.12 看门狗（已定稿）

10 秒级检测 camera.log 匹配错误→重启 vio.service，冷却 180 秒（60 秒会重启风暴）。

### 7.13 ★★★ 640@15 下飞行发散（当前核心问题，未解决）

**现象**：手持晃动 VIO 位置漂（40 米级）；飞行触发发散保护（位置漂到 87 米），VISION 锁死 \[发散保护]，EKF posH=nan（门控保护正常，EKF 未被污染）。

**铁证日志**：`ZUPT: passed disparity (0.064 < 0.200) + accepted |v_IinG| = 6.039`——**画面视差 0.064（几乎不动）但 IMU 速度 6m/s**—— 图像与运动严重不一致。

**根因**：640×480@15fps 下飞行 —— 帧间隔 67ms，6m/s 时每帧移动 0.4 米，加红外运动模糊 ——**特征匹配失败 / 视差失真→VIO 状态估计被带偏→发散**。

**对比**：848×480@30fps 下三次飞行验证全部正常（flags=367、VISION \[正常]）——**分辨率 / 帧率是唯一大变量**。

**结论**：**640@15 只适用于静止 / 地面低速，飞行必须 848@30**。恢复 848 = 硬件处理（换线 / 换口 / 供电），软件已备好切换命令（十节）。

### 7.14 ★ 手持晃动漂移（部分缓解）

**现象**：开机手持晃动，位置漂（无发散保护触发，但位置累积漂）。

**根因**：ZUPT `zupt_chi2_multipler: 0`（只看视差）+ 视差阈值 0.5 宽松 → **晃动中画面视差小（640@15 帧间失真）→ZUPT 误判静止→速度清零→位置漂**；同时外参 / 内参在线标定在开机初期未收敛，晃动把参数带偏。

**修复**：zupt\_chi2\_multipler=1.0（启用 IMU 一致性检验）+ zupt\_max\_disparity=0.2 + 关闭外参 / 内参在线标定。

**注意**：修复后静止 ZUPT 仍正常（chi2 阈值 16.919）；但**640@15 下飞行仍发散**（见 7.13，属于帧率问题不是 ZUPT 问题）。



***

## 八、已知问题与限制



| 问题                        | 严重程度        | 说明 / 对策                                      |
| ------------------------- | ----------- | -------------------------------------------- |
| **D430 REC error→640@15** | **高（当前主线）** | **飞行不可用**；恢复 848 需换 USB 线 / 换口 / 供电（软件已备好切换） |
| 640@15 飞行发散               | **高**       | 见 7.13，恢复 848 后验证                            |
| 手持晃动漂移                    | 中           | 已缓解（ZUPT chi2 + 视差 0.2），640 下仍比 848 差        |
| 纯 VIO 漂移                  | 中           | 无回环；门控自动保护 EKF                               |
| 偏航漂移                      | 中           | 无磁力计 + 无视觉偏航，IMU 积分                          |
| 视觉高度抖动（悬停时高时低）            | 中           | HGT\_REF=3 敏感；可考虑 HGT\_REF=1（未决策）            |
| /tmp 日志断电丢失               | 低           | 需持久化改路径                                      |



***

## 九、待办事项

### ✅ 已完成



1. EKF 融合打通（EV\_CTRL=3，flags=367 验证）

2. 三次真实飞行验证（848@30 时代）

3. odomimu 不发布根因修复（ZUPT+Propagator 补丁）

4. 外参标定（ENU 版）

5. 桥接自动重连、看门狗 180s、VIO 健康门控

6. ZUPT 防误触发（chi2 + 视差 0.2）

7. 相机 640@15 应急适配

### 🔴 接手方第一优先



1. **恢复 D430 848@30**：换 USB 线 / 换口 / 检查供电 → `grep 'Open profile' /tmp/camera.log`确认 848 → 执行十节切换命令 → **飞行验证**（重点：确认 VISION \[正常]、EKF flags=367、位置不漂）

2. **飞行验证 640 vs 848 对比**（848 恢复后做基线）

### 中优先级



1. 悬停高度抖动修复决策（HGT\_REF=1 vs 调视觉 z 协方差）

2. 外参在线标定收敛后固化（可选，当前关闭状态是稳定的）

3. 机场自动起降联调

4. GPS 融合（室外）、视觉识别跟随（Apriltag / 手掌）

### 低优先级



1. 禁用桌面环境、日志持久化



***

## 十、常用操作命令

### 10.1 服务管理



```
systemctl status vio.service

sudo systemctl restart vio.service

sudo systemctl stop vio.service      # 调试串口前必停

systemctl is-enabled vio.service

systemctl status watchdog\_camera.service
```

### 10.2 日志查看



```
tail -f /tmp/vio.log /tmp/vio\_bridge.log /tmp/camera.log

grep '已发送VISION' /tmp/vio\_bridge.log | tail   # \[正常]/\[发散保护]

grep 'EKF状态' /tmp/vio\_bridge.log | tail        # flags/视位/视速

grep -E 'ZUPT' /tmp/vio.log | tail               # 特征/速度/chi2
```

### 10.3 ROS2 检查



```
source /opt/ros/humble/setup.bash

export ROS\_DOMAIN\_ID=42; export ROS\_LOCALHOST\_ONLY=1

ros2 topic hz /imu          # \~150Hz

ros2 topic hz /odomimu      # \~100Hz（静止也发）

ros2 topic hz /camera/camera/infra1/image\_rect\_raw  # 15或30Hz
```

### 10.4 ★ 相机分辨率切换（恢复 848 后执行）



```
\# 1) 确认相机真实输出848: grep 'Open profile' /tmp/camera.log

\# 2) 切回848内参/分辨率:

sed -i 's/intrinsics: \\\[318.66, 318.66, 319.38, 240.207\\]/intrinsics: \[422.216, 422.216, 423.231, 240.207]/g; s/resolution: \\\[640, 480\\]/resolution: \[848, 480]/g' \~/vio\_ws/src/open\_vins/config/d430/kalibr\_imucam\_chain.yaml

\# 3) 重启:

sudo systemctl restart vio.service

\# 4) 验证: grep -E 'ZUPT' /tmp/vio.log | tail  → 特征>15
```

### 10.5 重新编译 OpenVINS



```
sudo systemctl stop vio.service

cd \~/vio\_ws && source /opt/ros/humble/setup.bash

colcon build --packages-select ov\_msckf --parallel-workers 2

sudo systemctl start vio.service
```

### 10.6 ZUPT / 在线标定参数修改（当前值勿乱改）



```
\# 文件: \~/vio\_ws/src/open\_vins/config/d430/estimator\_config.yaml

\# zupt\_chi2\_multipler: 1.0   (0=只看视差,勿回0)

\# zupt\_max\_disparity: 0.2    (0.5太宽松会误触发)

\# calib\_cam\_extrinsics: false  (用ENU外参)

\# calib\_cam\_intrinsics: false  (用出厂内参)

\# calib\_cam\_timeoffset: true   (保留在线)
```



***

## 十一、调试指南

### 11.1 VIO 不输出 odomimu



1. `grep odom-dbg /tmp/vio.log | tail` → `init=1`才发布

2. `ros2 topic hz /imu` ≥100Hz；`ros2 topic hz /camera/camera/infra1/image_rect_raw`有流

3. `grep 'successful initialization' /tmp/vio.log | tail`

4. 补丁检查：VioManager.cpp 应含 2 处`timelastupdate = message.timestamp;`；Propagator.cpp 含 50ms 窗口扩展

5. 特征 0：抓帧确认画面 → 画面正常则查**内参 /resolution 是否与相机实际输出匹配**

### 11.2 飞控收不到 VIO / 融合异常



1. `已发送VISION`标签：`[正常]`正常；`[发散保护]`=VIO 发散门控锁定（EKF 安全）

2. `EKF状态`：解锁后 flags=367（视位 + 视速）；posH=nan = 视觉水平位置被判不可信

3. 串口：桥接日志 "连接 PX4 成功"、`ls /dev/ttyACM*`

4. EKF2\_EV\_CTRL 必须是 3（不是 11）

### 11.3 VIO 发散排查（重要）



1. **先确认相机分辨率**：`grep 'Open profile' /tmp/camera.log`——**640@15 时飞行发散是预期行为，先恢复 848**

2. 看 ZUPT 日志：`passed disparity (X < 0.200)` + `accepted |v| = Y`——**X 很小但 Y 很大 = 图像与运动不一致（帧率 / 模糊 / 时间偏移问题）**

3. 时间偏移：`grep timeoffset /tmp/vio.log`—— 应稳定在 0.004 左右

4. 外参：确认是 ENU 版（7.9）

5. 静止测试：放下静止 10 秒 → `发散保护`后应自动恢复`[正常]`（门控 RECOVER 逻辑）

### 11.4 RViz 看不到图像

Fixed Frame=`global`；话题`/trackhist`；同一 ROS 域。

### 11.5 桥接崩溃 / 连接失败



1. 桥接日志有无`重连`/`TypeError`（加固版自动重连）

2. 确认串口没被 QGC / 旧进程占用

3. `pkill -9 -f vio_bridge; sudo systemctl restart vio.service`



***

## 十二、交接说明（接手方必读）

### 当前状态（2026-09-09）



* **VIO 全链路已打通**：相机→VIO→odomimu（静止即发）→桥接 VISION→EKF 融合

* **三项源码级修复已部署**：Propagator 窗口、ZUPT timelastupdate、桥接自动重连

* **外参已标定**（ENU 版 + 8cm）；ZUPT 防误触发已配置（chi2 + 视差 0.2）；在线标定已关闭（外参 / 内参）

* **关键卡点：D430 硬件 REC error → 640@15 → 飞行发散**。当前系统在 640@15 下**静止 / 地面可用，飞行不可用**

* 开机自启 + 看门狗已配置，插电自动运行

* 飞控参数（EV\_CTRL=3 等）由用户在 QGC 维护

### 接手方第一任务（按顺序）



1. **恢复 D430 848@30**：换 USB 线→换 USB 口→检查供电（REC error 是硬件问题，软件无法绕过）

2. 确认 848：`grep 'Open profile' /tmp/camera.log`

3. 执行 10.4 切换命令（内参 /resolution 回 848）→重启

4. 飞行验证：VISION \[正常] 标签、EKF flags=367、位置不漂、无发散保护

5. 记录 848@30 飞行基线（与 640@15 对比）

### 测试注意事项



* 解锁前静止几秒让 EKF 收敛

* 起飞后多飞绕圈 / 8 字（在线时间偏移收敛）

* **当前 640@15 下不要飞行**（必然发散，门控会保护但 VIO 定位失效）

* 降落到低纹理场地 VIO 可能发散 → 门控自动保护（EKF 靠光流 / 气压）

### 联系人信息



* 部署者：（请填写）

* 交接日期：2026-09-09



***

*本文档随项目进展持续更新*