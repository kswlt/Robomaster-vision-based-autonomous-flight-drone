# VIO 验证基线（D430 双目 + PX4 IMU + OpenVINS）

> **本文档是唯一权威结论来源。**
> 仓库中更早的审计文档、commit message 与脚本注释中的结论，凡与本文冲突者，
> 一律以本文为准；本文明确标注为 `未验证 / UNVERIFIED` 的内容不得被当作结论使用。

```
VALIDATED HEAD:        4310ada593eb81b55a550dae83f758c8d22655cf  (origin/d430)
VALIDATED DATE:        2026-09-23
VALIDATED HOST:        Orange Pi 5 (RK3588, 6 usable cores, ROS 2 Humble)
VALIDATED CONFIG HASH: (见下表)
VALIDATED BAG HASH:    (见下表)
```

硬件事实（本次实测，非文档转述）：

| 项 | 实测值 | 来源 |
|---|---|---|
| 相机 | RealSense D430, SN `938422073656`, FW `5.17.3.10` | `rs-enumerate-devices` |
| 相机 USB | **5000M SuperSpeed**（Bus 02） | `lsusb -t` |
| PX4 串口 | `1b8c:0036 MicoAir743AIO`，CDC-ACM **12M**（USB FS） | `lsusb -t` |
| 双目基线 | **50.1375 mm** | 硬件直读 |
| realsense-ros | v4.58.3 / Librealsense v2.58.3 / pyrealsense2 2.58.4 | 节点日志 |
| 图像模式 | 848×480 @ 30（infra1+infra2，depth/color 关闭） | 相机日志 + bag 统计 |

---

## 0. 一句话结论

动态漂移不是单一原因，而是**三个独立缺陷叠加**：

1. **ZUPT 被本地代码修改 + 配置未同步，导致完全失效，而日志伪装成正常工作**（确证）；
2. **IMU 时钟映射把传输抖动写进惯导时间轴，且缺少主机/PX4 频率比修正**，使相机-IMU 对
   准随时间漂移（确证，合成数据定量 + 历史数据吻合）；
3. **运行配置、启动脚本、systemd 单元与仓库严重不一致**，导致任何实验结论都无法归属
   到确定的代码与配置（确证）。

**历史文档断言的"IR speckle 是动态漂移主因"在本环境下被实测降级为 `未验证`**：
投影器对图像的最大贡献只有约 5 个灰度级（详见 §3.1）。

---

## 1. 方法论：为什么本次结论可信

任务书要求"不能只看 Git 里某个文件"。本次调查遵守以下约束：

- **冻结优先**：任何修改前先记录 `git rev-parse HEAD`、`git status`、以及**板子上实际
  运行文件**的 SHA256（见 `_evidence/` 与冻结包 `vio_audit_freeze_20260923T121817.tar.gz`）。
- **区分三层事实**：Git 仓库 / 板子运行目录 / 进程实际加载值，三者分别取证。
- **单变量 A/B**：每一轮只改一个参数，其余字节完全不变（`mksweep.py` 保证）。
- **同一 immutable bag**：所有参数实验复用同一个 SHA256 固定的 bag。
- **失败可复现**：离线回放管线（`replay_one.sh` + `analyze2.py`）在独立
  `ROS_DOMAIN_ID=43` 上运行，不影响其他进程，且可重复执行。

### 1.1 一个必须记录的环境陷阱

本机运行的所有 VIO 进程都设置了 `ROS_LOCALHOST_ONLY=1`。任何新起的 ROS 2 进程若
使用默认值 `0`，**在 60 秒内完全发现不到任何节点或话题**（实测：`=1` 时 5 秒内发现
8 节点/36 话题；`=0` 时 60 秒内 0 个）。这会让 `ros2 param get` / `ros2 topic hz` 等
全部失效，并可能让此前的排查得出"参数不存在"之类的错误结论。

**规则：任何诊断命令都必须显式 `export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=42`。**

---

## 2. 运行现实 vs 仓库现实（审计）

### 2.1 配置文件

| 文件 | Git HEAD | 板子实际加载 | 判定 |
|---|---|---|---|
| `estimator_config.yaml` | `7dc4b109…` | `7dc4b109…` | ✅ 一致 |
| `kalibr_imu_chain.yaml` | `9c4c8222…` | `9c4c8222…` | ✅ 一致 |
| `kalibr_imucam_chain.yaml` | `fcfc2457…` **timeshift=+0.001256** | `33544c12…` **timeshift=−0.010** | ❌ **不一致** |
| `vio_bridge_combined.py` | `214794d2…` | `214794d2…` | ✅ 一致 |

运行配置目录 `/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430/` **不是 git 仓库**，
且包含 8 个手工调参备份：

```
kalibr_imucam_chain.yaml.bak-20260919
kalibr_imucam_chain.yaml.bak-neg08deg-20260923022816
kalibr_imucam_chain.yaml.bak-int640-20260923022511
kalibr_imucam_chain.yaml.bak-7deg-20260923024126
kalibr_imucam_chain.yaml.bak-mangled-20260923025152
kalibr_imucam_chain.yaml.bak-inv7-20260923033201
kalibr_imucam_chain.yaml.bak-ts010
kalibr_imucam_chain.nominal.yaml
```

这些文件名本身就是"手工猜外参/时间偏移"的物证（`-0.8°`、`-7°`、取逆、640 内参）。

**运行时确认（OpenVINS 自己的打印）**：

```
LOADED_CONFIG_PATH=/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430/estimator_config.yaml
LOADED_CAMERA_IMU_TIME_OFFSET_SEC=-0.010000000
LOADED_CAMERA_0_INTRINSICS=422.216 422.216 423.231 240.207  0 0 0 0
   EXTRINSICS_Q_ItoC_P_IinC=-0.500805 0.506195 -0.493205 0.49971 0.0222792 0.0226863 -0.076766
```

### 2.2 启动链（共 5 套，且 systemd 指向 git 中不存在的版本）

```
/etc/systemd/system/vio.service
    → ExecStart=/home/orangepi/kswlt/tools/start_vio_systemd.sh    sha 37c41367…
git 仓库中的 start_vio_systemd.sh                                  sha 24b6a43c…   ❌ 不一致
/home/orangepi/kswlt/tools/start_vio.sh                            sha 2e335a42…
/home/orangepi/kswlt/gh_d430/start_vio.sh                          sha 2e335a42…
/home/orangepi/kswlt/vio_ws/start_vio.sh                           sha 7d98dd54…   ❌ 内容错误
/etc/systemd/system/vio.service                                    sha 7223256a…  ❌ ≠ git 4ab96de1…
/home/orangepi/kswlt/gh_d430                                    停在 0b95bab，落后 9 个 commit
```

`:…/vio_ws/start_vio.sh` 使用的是 **640×480**、旧的 `imu_bridge.py`、以及会向 PX4
写入的 `vio_to_px4.py` —— 误用它会得到完全不同的系统。

`vio.service` 在取证时处于 **disabled / inactive**，即当时的运行栈是手工拉起的。

### 2.3 `enable_ir_emitter` 是一个不存在的参数

历史脚本（手动版）传入 `enable_ir_emitter:=false`。实测该 realsense-ros 版本的
`rs_launch.py` **没有**这个参数，节点参数列表里也没有 `emitter_enabled` / `laser_power`
的 launch 入口。**因此"启动时关闭 IR"从未真正被执行过。**

---

## 3. 已确证的根因

### 3.1 IR speckle —— 实测降级（原"主因"结论不成立）

用 pyrealsense2 **直接控制硬件**并读回验证（写入确实生效：`laser_power<-360 readback=360.0`、
`emitter_enabled<-0 readback=0.0`），固定曝光 8500，逐档扫描：

| laser_power | infra1 mean | infra2 mean |
|---|---|---|
| 0 | 93.84 | 92.02 |
| 150 | 95.44 | 96.15 |
| **360（最大）** | **98.90** | **100.97** |
| `emitter_enabled=0`（LP=360） | 93.08 | 91.23 |

**把激光功率从 0 拉到最大，图像只亮约 5 个灰度级（5.4%）。**

历史 bag 对比：`DYN50`(凌晨 03:12, mean=99.8) vs `LASEROFF3`(早上 07:56, mean=23.2)，
相差 **76 级** —— 远大于投影器能做到的 5 级。**该差异主要来自环境光/曝光，而不是投影器。**

结构原因：硬件 `emitter_always_on = 0`，而当前配置 `enable_depth: false`（无深度流）。

**结论：`IR speckle 是动态漂移主因` → `未验证`（本环境下效应 ≤5%，不足以解释历史
494 m vs 0.65 m 的差异）。历史对比极可能存在混淆变量。**

> 注意：这并不表示投影器无害。真正待验证的是**运动时**散斑去相关对 KLT 的影响，
> 该实验需要暗环境下的配对采集，尚未进行 → 见 §6。

### 3.2 ZUPT 完全失效，而日志伪装成正常

三个版本的 `ov_msckf/src/update/UpdaterZeroVelocity.cpp`：

| 版本 | 关键条件 | `chi2_multipler=0` 的行为 |
|---|---|---|
| 上游原始（`…/trajectory-fix-20260913/UpdaterZeroVelocity.cpp.before`） | `if (!disparity_passed && (chi2 > mult*chi2_check \|\| vel > max))` | **OR 语义：disparity 通过即接受** ✅ 与官方注释 `set to 0 for only disp-based` 自洽 |
| 第一次本地修改（`…/imu-recovery-fix-20260913/…before`） | `if (!disparity_passed \|\| !inertial_passed)` | **改为 AND：永远拒绝** ❌ |
| **当前运行版本** | 同上 AND（仅移除 velocity 判据） | **永远拒绝** ❌ |

当前代码（`UpdaterZeroVelocity.cpp:246-255`）：

```cpp
const double chi2_limit = _options.chi2_multipler * chi2_check;   // 0 * chi2_check = 0
const bool inertial_passed = (chi2 <= chi2_limit);                // 恒为 false
if (!disparity_passed || !inertial_passed) {
    PRINT_DEBUG(YELLOW "[ZUPT]: rejected ...");                   // INFO 级别下不可见
    return false;
}
```

**实测（实时日志 + 离线回放双重确认）**：

```
"[ZUPT]: passed disparity"  出现 23832 次
"[ZUPT]: accepted"          出现 0 次
```

`passed disparity` 只是"视差判据通过"，随后立刻被 chi2 判据否决；而否决日志是
`PRINT_DEBUG`，在 `verbosity: "INFO"` 下不输出。**这正是任务书第十一节担心的
"配置显示 ZUPT ON、实际永远 reject"，现已确证。**

### 3.3 IMU 时钟映射：抖动写入时间轴 + 缺少频率比修正

物理分解：

```
arrival_offset = t_ros_receive − t_px4_sensor
               = 真实时钟偏差 + USB/MAVLink 传输 + Linux 调度 + Python 解析延迟
```

对三种策略做**合成数据定量自检**（`imu_clock_mapper.py`，200 Hz，真实 host/px4
漂移 −953 ppm，基础延迟 3 ms + 偶发 50–300 ms stall）：

| mode | dt_std | dt_max | **axis_err_ppm** |
|---|---|---|---|
| `lower`（旧代码，lower-envelope） | 2.58e-5 | 5.000 ms | −28.5 |
| `lower`（**正**漂移场景） | **1.97e-6** | 5.000 ms | **−1004.2** |
| `ema005`（当前代码，α=0.05） | **3.23e-4（×12）** | **19.78 ms（×4）** | −17.4 |
| `slow`（本次新增） | **2.78e-5** | 6.64 ms | **−15.0** |

长时场景（600 s）：

| mode | 场景 | dt_std | dt_max | axis_err_ppm |
|---|---|---|---|---|
| `lower` | 正漂移 | 4.08e-5 | 5.000 ms | **−114.0** |
| `lower` | 负漂移 | 2.55e-5 | 5.000 ms | −2.9 |
| `ema005` | 正漂移 | 3.24e-4 | 19.94 ms | −0.8 |
| **`slow`** | **正漂移** | **1.35e-5** | 6.65 ms | **−32.7** |
| **`slow`** | **负漂移** | **1.27e-5** | 6.64 ms | **−0.2** |

要点：

* **`lower` 是方向依赖的**：负漂移时 dt 干净得"完美"（std 1.97e-6）却在正漂移下
  产生 −1004 ppm 的时间轴漂移。**这精确解释了"静止时看起来稳定、一动就漂"**，
  并与历史实测的 −0.9 ms/s、−1.058 ms/s 吻合。
* **`ema005` 把传输抖动写进惯导时间轴**（dt_std 放大 12 倍，dt_max 近 20 ms ≈ 4 个采样周期），
  任务书第六节的担忧成立。
* 两者都**缺少频率比修正**：即使 offset 完美，IMU 轴仍以 PX4 速率推进而相机以主机速率
  推进。−1000 ppm 即 **3.6 秒/小时**，任何固定的 `timeshift_cam_imu` 都只有秒级的有效期。
* `slow` 是唯一同时做到「轴速率正确」+「dt 抖动最小」的策略。

**真实历史数据的旁证**（前一次采集的原始 trace，`px4_timebase_summary.json`）：
`dt mean=0.005269 / std=0.009334 / max=0.997864`（存在近 1 秒空洞），
`arrival_offset` 斜率 **−1.058e-3 s/s**，与合成场景的 −1000 ppm 量级一致。

### 3.4 `+1e-6` 时间戳钳位：静默改写

旧代码：

```python
if self.last_imu_stamp is not None and stamp <= self.last_imu_stamp:
    stamp = self.last_imu_stamp + 1e-6     # 无计数、无日志、无 fail-fast
```

若正常 dt ≈ 5 ms 而被改写成 1 µs，会严重破坏惯导积分，且**完全不留痕迹**。
现已改为显式计数 + 日志 + 连续触发时重置时钟映射（`MAX_CONSECUTIVE_REPAIRS = 5`）。

### 3.5 实时处理能力不足（"离线好、实时差"的关键）

* `[TIME]` 的语义是**单帧 CPU 耗时**（`ROS2Visualizer.cpp:481`），不是帧间隔；
  且 `behind` 字段在源码里被乘了 `100.0`，打印值需 ×10 才是毫秒。
* 实时实测单帧耗时：mean **33.2 ms**、p50 **36.7 ms**、max 111.7 ms，而帧周期 33.3 ms
  → **一半以上帧的处理时间超过帧周期**。
* 实时实际只处理 **15.5 Hz**（25345 帧 / ≈1630 s），而 bag 实测相机稳定输出 **30.0 Hz**。
* `foxglove_bridge` 占用 **41% CPU / 678 MB**；另有 `/tmp/viz_web/server.py` 常驻。

**离线回放同一 bag（timeshift=−0.010）的结果**：

| 指标 | 实时观测 | 离线回放 |
|---|---|---|
| 静止段漂移（0–17 s） | ~5 mm | **6.1 mm** |
| 闭合误差 | — | **5.8 cm** |
| 最大单帧位置跳变 | **1.2348 m** | **2.0 cm** |
| >10 cm 的跳变次数 | 多次 | **0** |
| 最终位置误差 | **1.77 m（且之后 750 s 冻结不动）** | 5.8 cm |

这正落在任务书第二十八节的判断分支上：**离线 bag 稳定、实时漂移 → 优先查
timestamp / runtime scheduling / 实际启动配置 / USB**。

### 3.6 相机第一帧的时间戳是坏的（真实数据缺陷）

`LASEROFF3` bag 实测：第一个图像帧的 `header.stamp` 比实际早 **14578.2 秒（4.05 小时）**，
其余 1930 帧 dt 均为 33.34 ms。相机的 `arrival_offset` 因此出现 max = 14578 s 的离群值。

该帧会让 OpenVINS 的相机队列出现一个置于极早时刻的样本。**当前启动链没有任何防护。**

### 3.7 外参平移与真实基线不符

由 yaml 的 `T_imu_cam` 平移**反算 OpenVINS 内部语义**（用 `−R^T·t`）：

```
yaml cam0 t = (0.077055, 0.022100, 0.021867)
反算 P_IinC = (0.0222792, 0.0226863, −0.076766)
日志打印     = (0.0222792, 0.0226863, −0.076766)     ← 完全吻合
```

即 OpenVINS 内部把 yaml 的 `T_imu_cam` **取逆**存为 `T_ItoC`；且
`opencv_yaml_parse.h:492-497` 把 `T_imu_cam` 与 `T_cam_imu` 当作同义词互换。

而由此算出的双目基线：

```
yaml 外参基线            = 46.88 mm
CameraInfo P[3]/fx       = 50.14 mm
硬件直读 Stereo Baseline = 50.1375 mm
```

**误差 6.5%。** 结合 8 个手工调参备份，外参的可信度判定为 **`未标定 / UNVERIFIED`**，
不得再被引用为"已标定值"。

### 3.8 初始化：阈值无判别力，但并非完全无保护

`InertialInitializer.cpp:104-158`：

```cpp
disparity_detected_moving = (avg_disp > params.init_max_disparity);
bool is_still = (!moving_1to0 && !moving_2to1);
if ((has_jerk && wait_for_jerk) || (is_still && !wait_for_jerk)) → 静态初始化
```

实测 disparity 仅 **0.048–0.141 px**，阈值 `init_max_disparity: 10.0` 因此等价于
"永远判为静止"，**该判据本身不携带信息**。

**但**静态初始化内部还有 IMU 检查（`init_imu_thresh: 1.5`，加速度方差）——
实时日志中从未出现 `too much IMU excitation`，说明该保护在起作用。
因此"会在运动中错误完成初始化"的风险**存在但被部分缓解**；
平滑慢速平移仍可能同时骗过两道判据。`0.3 vs 10.0` 的 A/B 见 §5。

### 3.9 初始化前的 IMU 窗口失败

实时日志出现 **13 次** `[init-s]: unable to select window of IMU readings, not enough readings`
（离线回放同样出现 8 次）。这是静态初始化器在 2 s 窗口内凑不齐 IMU 读数，
与 IMU 时间戳质量/连续性直接相关。

### 3.10 初始化输出的 bias 可疑

```
[init]: bias gyro  = -0.0000, 0.0000, 0.0000     ← 恰好为 0
[init]: bias accel = -0.0000, 0.0000, -0.0027
[init]: velocity   = 0.0000, 0.0000, 0.0000
```

真实 IMU 的陀螺零偏不可能精确为 0。该值保留两位有效数字打印，需在后续用更长窗口
复核（→ §6）。

### 3.11 静止期间加速度计 bias 单向爬升

实时日志：静止段内 `ba_y` 从 0 单向爬升到 **0.10 m/s²**（约 70 s），随后回落。
`|ba|` 峰值 0.0934（超过任务书给出的 0.1 m/s² 关注线边缘）。

---

## 4. 已实施的修复

| # | 文件 | 内容 |
|---|---|---|
| 1 | `imu_clock_mapper.py`（新增） | 三策略可切换的时钟映射状态机：滑动窗口 P5 offset + 长期鲁棒回归频率比 + 显式钳位计数 + 连续违规重置。含合成数据自检。 |
| 2 | `vio_bridge_combined.py` | 改用 `ImuClockMapper`；新增 `imu_clock_mode` / 诊断参数；逐包 CSV 记录 `sensor_time, arrival_time, arrival_offset, clock_offset, stamp, dt, repaired, repaired_orig_dt, scale_ppm, gated`；每 30 s 打印一次统计摘要；串口重连时重置映射。 |
| 3 | `config/d430/estimator_config.yaml` | `zupt_chi2_multipler: 0 → 1`（0 在本树中等价于关闭 ZUPT），并写明原因；为 `init_max_disparity` 标注实测证据与 A/B 状态。 |
| 4 | `scripts/vio_precheck.py`（新增） | fail-closed 启动自检：D430 存在 / USB3 5000M / PX4 串口 / **强制关闭并读回验证** emitter 与 laser_power / 分辨率 / 内参 vs YAML / 帧率 / 双目时间戳同步 / IMU 速率与单调性 / ZUPT 语义 / 打印 CONFIG_SHA256。任一关键项失败即拒绝启动 estimator。 |
| 5 | `start_vio.sh`（重写） | 唯一权威启动脚本：6 阶段自检后依次启动；删除无效的 `enable_ir_emitter`；把"晃动相机初始化"改为**保持静止**；foxglove 默认关闭且显式警告其 CPU 代价；`send_vision_to_px4` 硬编码 false。 |
| 6 | `start_vio_systemd.sh`（重写） | 降为薄包装（保留 flock + 故障锁存），启动逻辑全部委托 `start_vio.sh`，使两条路径在结构上不可能再分叉。 |

---

## 5. 验收结果（同一 immutable bag 的单变量 A/B）

> 所有数字均来自 `replay_one.sh` 在 `ROS_DOMAIN_ID=43` 的离线回放 + `analyze2.py` 统计，
> 每个配置只改一个参数。

### 5.1 timeshift_cam_imu 扫描

见 §5.4 汇总表（`ts_m15 / ts_m12 / ts_m10 / ts_m08 / ts_m05 / ts_000 / ts_p1256 / ts_p05`）。

### 5.2 ZUPT 语义

`zupt_m0`（当前破损值）/ `zupt_m1`（修正后）/ `zupt_m10`（极宽松）/ `zupt_off`（关闭）。

### 5.3 静态度初始化阈值

`init_d03`（0.3） vs `init_d10`（10.0）。

### 5.4 汇总

（本节在全部回放完成后填充真实数字。）

---

## 6. 尚未验证 / 已知残余问题

以下项目**没有实验证据**，不得当作结论：

| 项 | 状态 |
|---|---|
| 运动时散斑去相关对 KLT 的影响（暗环境配对采集） | `未验证` |
| 陀螺零偏初值打印为精确 0 是否真实 | `未验证` |
| IMU 噪声参数是否符合 Allan 方差 | `未验证`（历史为经验值，非标定值） |
| 相机-IMU 外参（旋转 + 平移 + 时延）完整 Kalibr 标定 | `未验证`（当前外参判定为未标定，基线误差 6.5%） |
| 相机第一帧 4 小时时间戳跳变的根因（RealSense 侧） | `未验证`（已确认现象与幅度） |
| 长时间（小时级）相机-IMU 对齐漂移的实测 | `未验证`（修复已实现，待长时采集） |
| 纯旋转虚假位移的最终验收数字 | 依赖离线回放分析（`rot_*` 指标） |
| 动态最大漂移 / 0.5 m 往返闭合 <10 cm 的**实时**验收 | 需真实运动，回放近似不能完全替代 |

---

## 7. 复现步骤

```bash
# 0) 环境（必需，否则看不到任何节点/话题）
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=42

# 1) 单次离线回放（独立 domain，不影响其他进程）
bash ~/kswlt/vio_replay/replay_one.sh \
     ~/vio_data/20260922T235522Z_LASEROFF3/bag \
     ~/kswlt/vio_replay/configs/base \
     ~/kswlt/vio_replay/out/baseline_ts010 baseline_ts010 43

# 2) 指标
python3 ~/kswlt/vio_replay/analyze2.py \
     ~/kswlt/vio_replay/out/baseline_ts010 \
     ~/vio_data/20260922T235522Z_LASEROFF3/bag baseline_ts010

# 3) 任意单变量变体
python3 ~/kswlt/vio_replay/mksweep.py ~/kswlt/vio_replay/configs/base \
     /tmp/cfg_x zupt_chi2_multipler=1

# 4) 时钟映射策略自检（合成数据，含方向依赖性证明）
python3 ~/kswlt/vio_ws/vio_bridge/imu_clock_mapper.py

# 5) 启动前自检（fail-closed）
python3 scripts/vio_precheck.py hw     config/d430 42
python3 scripts/vio_precheck.py camera config/d430 42   # 相机节点需已运行
python3 scripts/vio_precheck.py imu    config/d430 42   # bridge 需已运行

# 6) 权威启动 / 停止
./start_vio.sh -d 42            # 手动
./start_vio_systemd.sh          # systemd 走同一条路径
pkill -INT -f run_subscribe_msckf; pkill -INT -f vio_bridge_combined; pkill -INT -f realsense2_camera
```

`/odomimu` 是估计器原始输出；`/odomimu_viz` 仅供 Foxglove 观察，
**任何地图 / 控制 / 轨迹跟踪 / PX4 用途都不得使用节流后的可视化话题**。
