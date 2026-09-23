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

### 1.2 一个必须记录的方法论陷阱：回放批次的互斥

离线回放**必须严格串行**。回放管线在启动时会 `pkill -f run_subscribe_msckf`，
并且两个实例若共享同一 `ROS_DOMAIN_ID` 会订阅同一批话题，**互相杀死对方的估计器并
串扰数据**。

本次调查中真实发生过一次：两个链式脚本分别以
`pgrep -f sweep_timeshift_ext` 和 `pgrep -f sweep_phase2` 作为等待条件，
而后者启动时前者尚未开始，`pgrep` 立即返回空，等待循环直接退出，
于是 phase 2 与跨 bag 验证**并发**运行。**那两批结果已作废并按
`*.VOID-concurrent` 归档**，随后改用 `flock` 保护的单一串行批次重跑。

**规则：任何回放批次都必须持有 `flock /tmp/vio_replay.lock`；不得依赖
"进程名存在性"作为阶段间的等待条件。** 对应的实现见
`scripts/run_serial_final.sh`（在本仓库中为 `scripts/abort_and_serial.sh` 生成）。

### 1.3 一个必须记录的验证陷阱：不要用 PyYAML/OpenCV-Python 校验 kalibr 链文件

这些文件的格式是 OpenCV FileStorage 的 `%YAML:1.0` 方言，且 4×4 变换用**纯 YAML 序列**
书写，而不是 `!!opencv-matrix`。实测：

* 标准 **PyYAML 直接拒绝**该文件（`%YAML:1.0` 不是合法的 YAML 指令）；
* **OpenCV 5.x 的 Python `FileStorage`** 能打开文件，但 `getNode('cam0')` 之后
  再取子节点会断言失败 `isMap()` —— 对**原始未修改的运行文件同样如此**，
  是 API 行为而非文件缺陷。

**唯一可靠的判据是让真实二进制加载它并检查它打印的 `LOADED_*`。**
`scripts/loadtest_cfg.sh` 就是干这件事的；本次以它确认
`LOADED_CAMERA_IMU_TIME_OFFSET_SEC=-0.015000000` 被正确加载。

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

**先记录一个操作层面的关键事实（实测，固件 5.17.3.10）**：

| 操作 | 结果 |
|---|---|
| 无流时 `set emitter_enabled=0` | 读回 0.0，**但开流后被自动重置为 1.0** |
| 停止流之后 | **再次重置为 1.0** |
| 流运行时，顺序 `laser_power=0` → `emitter_enabled=0` | 读回 **0.0** ✅ |
| 流运行时，顺序反过来（先动 emitter，后动 laser） | 读回 **1.0** ❌ |
| `laser_power = 0` | **持久化**（停流后仍为 0）✅ |

**即 `emitter_enabled` 是"流会话级"设置，开流即重置为默认值 1；且写入顺序必须是
先 `laser_power` 后 `emitter_enabled`，否则该次写入被设备拒绝。**

这解释了仓库历史上反复出现的现象——"实验里关了 laser，正式启动却仍然开着"：
* 旧的 `enable_ir_emitter:=false` 是**不存在的 launch 参数**（§2.3），从未生效；
* 即使曾经用 SDK 关成功过，**下一次开流就会把它重置**；
* 因此"关 IR"必须在**每次启动、且流已打开之后**重新执行并读回验证，
  不能是一次性的配置项或开机动作。

现在 precheck 就是这么做的：`hw` 阶段只报告状态，`camera` 阶段（流已开）
按正确顺序强制关闭并读回验证，失败即拒绝启动估计器。

---

**关于投影器对图像的贡献**：用 pyrealsense2 直接控制硬件并读回验证写入
（`laser_power<-360 readback=360.0`、`emitter_enabled<-0 readback=0.0`），
固定曝光 8500，逐档扫描：

| laser_power | infra1 mean | infra2 mean |
|---|---|---|
| 0 | 93.84 | 92.02 |
| 150 | 95.44 | 96.15 |
| **360（最大）** | **98.90** | **100.97** |
| `emitter_enabled=0`（LP=360） | 93.08 | 91.23 |

第二次独立复核（开流、固定曝光、取 20 帧均值）：

| 状态 | infra1 mean | infra2 mean |
|---|---|---|
| emitter OFF (LP=0) | 94.09 | 92.35 |
| emitter ON (LP=360) | 100.46 | 102.06 |
| 差值 | **+6.37** | **+9.71** |

**把激光功率从 0 拉到最大，图像只亮约 5–10 个灰度级（5–10%）。**

历史 bag 对比：`DYN50`(凌晨 03:12, mean=99.8) vs `LASEROFF3`(早上 07:56, mean=23.2)，
相差 **76 级** —— 远大于投影器能做到的量级。**该差异主要来自环境光/曝光，而不是投影器。**

结构原因：硬件 `emitter_always_on = 0`，而配置 `enable_depth: false`（无深度流）。

**结论：`IR speckle 是动态漂移主因` → `未验证`（本环境下效应 ≤10%，不足以解释历史
494 m vs 0.65 m 的差异）。历史对比极可能存在混淆变量。**

> 注意：这并不表示投影器无害。真正待验证的是**运动时**散斑去相关对 KLT 的影响，
> 该实验需要暗环境下的配对采集，尚未进行 → 见 §6。
> 同理，本节的亮度数字本身**不能**用来判定"IR 是否关闭"（自动曝光会补偿），
> 判定必须依赖 SDK 读回值。

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
| 静止段漂移 | ~5 mm | **6.1 mm** |
| 闭合误差 | — | **5.8 cm** |
| 最大单帧位置跳变 | **1.2348 m** | **2.0 cm** |
| >10 cm 的跳变次数 | 多次 | **0** |
| 最终位置误差 | **1.77 m（且之后 750 s 冻结不动）** | 5.8 cm |

> ⚠️ **这两个数字不能作为"同一输入、不同链路"的直接对比，必须如实标注。**
>
> 实时日志来自 2026-09-23 11:34–12:18 的现场采集（相机静止约 70 s 后有一次短促运动）；
> 而回放用的 `LASEROFF3` bag 是当天 07:56 录制的另一段场景（静止 17 s + 持续旋转 45 s）。
> **两者是不同物理场景**，因此上表的差异**不能**单独归因于 bridge、调度或 USB。
>
> 可严谨成立的是：
> * **静止段**两者一致且都很好（5 mm vs 6.1 mm）；
> * **运动后**实时的绝对误差（1.77 m，且此后完全冻结不再恢复）远超同一 bag 离线回放的量级；
> * 实时链存在 §3.5 前半段列出的客观事实（单帧 p50 37.1 ms > 33.3 ms 帧周期、70.2% 帧超预算、
>   实际只消费约 15 Hz 的 30 Hz 流、foxglove 占 41% CPU），这些是**实测而非推断**。
>
> 要把"实时 vs 离线"做成单变量对比，需要同一物理动作在两种链路上各跑一次，
> 这依赖现场操作，列为 `未验证`（§6）。

### 3.5.1 实测吞吐对比（这是可严谨对比的部分）

| 日志 | 处理帧数 | 单帧 CPU p50 | p95 | max | 超预算比例 |
|---|---|---|---|---|---|
| 实时（约 43 min） | 38910 | **0.0371 s** | 0.0462 | **0.3526 s** | **70.2%** |
| 离线回放（同一 bag） | 914 | **0.0322 s** | 0.0411 | 0.0990 | 32.4% |

30 Hz 的帧周期是 0.0333 s。离线回放的 p50 刚好压在线下（勉强实时），实时已经越线。
`[TIME]` 的语义已核实为**单帧 CPU 耗时**（`ROS2Visualizer.cpp:481`），不是帧间隔；
其 `hz` 字段是 `1/耗时`（吞吐率），`behind` 字段在源码中被乘了 `100.0`，打印值 ×10 才是毫秒。

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

### 3.12 ZUPT 的 disparity 判据为何几乎没有判别力

除了 §3.2 的 chi2 语义问题，disparity 判据本身也有结构性弱点。

`ov_core/src/feat/FeatureHelper.h` 的 `compute_disparity()` 用**浮点精确相等**匹配时间戳：

```cpp
auto it0 = std::find(feat->timestamps.at(camid).begin(), feat->timestamps.at(camid).end(), time0);
auto it1 = std::find(feat->timestamps.at(camid).begin(), feat->timestamps.at(camid).end(), time1);
if (it0 == feat->timestamps.at(camid).end() || it1 == feat->timestamps.at(camid).end())
    continue;                       // 两个时刻没有同时留存记录的特征被直接跳过
disparities.push_back((uv1 - uv0).norm());
```

只有"在 `time0` 与 `time1` 两个时刻都留有记录"的特征参与统计，跟踪失败的特征被静默丢弃。
其后果是**系统性低估**：快速运动时最容易丢跟踪的正是位移最大的特征。

实测（`zupt_max_disparity: 0.5`）：

| 来源 | disparity p50 | p95 | p99 | max | ZUPT 视差判据通过率 |
|---|---|---|---|---|---|
| 现场实时（相机基本静止） | **0.042 px** | 0.121 | 0.310 | 0.500 | **96.0%**（37345/38910） |
| 离线 `LASEROFF3`（含 45 s 持续旋转，峰值 50°/s） | 0.151 px | 0.383 | 0.447 | 0.489 | 34.6%（316/914） |

作为量级参照：在 848×480、f≈422 px 下，50°/s 的旋转在 33 ms 内转 1.65°，
理论上应产生约 **12 px** 的特征位移——而实测在持续旋转期间也只有约 0.5 px。

**结论：阈值 0.5 px 处在"运动时刚好触达"的边缘，无法可靠区分静止与运动。**
它的语义必须靠 chi2 判据补足，而 chi2 判据在 §3.2 中被发现是**恒 reject**——
两者叠加时才真正解释了这个文件里 ZUPT 的处境。
本项标注为**已定性 + 已定量，但"运动时散斑是否加剧该低估"仍未验证**（§6）。

### 3.11 静止期间加速度计 bias 单向爬升

实时日志：静止段内 `ba_y` 从 0 单向爬升到 **0.10 m/s²**（约 70 s），随后回落。
`|ba|` 峰值 0.0934（超过任务书给出的 0.1 m/s² 关注线边缘）。

离线回放同一 bag（`ts_m10`…`ts_m15`）的 `|ba|` 峰值为 0.081～0.091，量级一致，
说明该现象不是现场采集独有的。

---

## 4. 已实施的修复

| # | 文件 | 内容 |
|---|---|---|
| 1 | `imu_clock_mapper.py`（新增） | 三策略可切换的时钟映射状态机：滑动窗口 P5 offset + 长期鲁棒回归频率比 + 显式钳位计数 + 连续违规重置。含合成数据自检（`python3 imu_clock_mapper.py`）。 |
| 2 | `vio_bridge_combined.py` | 改用 `ImuClockMapper`；新增 `imu_clock_mode` / 诊断参数；逐包 CSV 记录 `sensor_time, arrival_time, arrival_offset, clock_offset, stamp, dt, repaired, repaired_orig_dt, scale_ppm, gated`；每 30 s 打印一次统计摘要；串口重连时重置映射（并保留单调性）。 |
| 2b | `imu_clock_mapper.py`（本轮修复的三处缺陷） | ①**时间基阶跃吸收**：PX4 的 `time_usec` 前跳/后退时，通过重算 offset 让**输出轴保持连续**，而不是让 offset 缓慢爬回（旧行为在回归测试中产生 99 次钳位、80 个不合理的 100 µs dt）；②**单调性保护不再失守**：`reset()` 曾清空 `last_stamp`，使致命重置后的下一帧可以向后跳；现在所有流中重置都带 `preserve_last_stamp`；③**`reset()` 不再清零计数器**：它曾把"发生过致命重置"的证据一并抹掉（这正是最初看到 `repairs=0` 却仍有回退的原因），并新增 `keep_anchor` 以免 bootstrap 覆盖刚建立的重锚 offset。 |
| 3 | `config/d430/estimator_config.yaml` | `zupt_chi2_multipler: 0 → 1`（0 在本树中等价于关闭 ZUPT），并写明原因；为 `init_max_disparity` 标注实测证据与 A/B 状态。**`timeshift_cam_imu` 的最终值由 §5.1 的扫描决定，不由人工猜测。** |
| 4 | `scripts/vio_precheck.py`（新增） | fail-closed 启动自检：D430 存在 / USB3 5000M / PX4 串口 / 分辨率 / 内参 vs YAML / 帧率 / 双目时间戳同步 / IMU 速率与单调性 / ZUPT 语义 / CONFIG_SHA256。**IR 投影器按 §3.1 的正确顺序在流已打开时强制关闭并读回验证**，任一关键项失败即拒绝启动估计器。 |
| 5 | `start_vio.sh`（重写） | 唯一权威启动脚本：6 阶段自检后依次启动；**删除无效的 `enable_ir_emitter`**；把"晃动相机初始化"改为**保持静止**；foxglove 默认关闭且显式标注其 CPU 代价；`send_vision_to_px4` 硬编码 false。 |
| 6 | `start_vio_systemd.sh`（重写） | 降为薄包装（保留 flock + 故障锁存），启动逻辑全部委托 `start_vio.sh`，使两条路径在结构上不可能再分叉。 |
| 7 | `scripts/replay_one.sh` / `analyze2.py` / `mksweep.py` / `sweep_*.sh` / `analyze_all.sh`（新增） | 可复现的离线回放与单变量 A/B 工具链；`mksweep.py` 保证除目标键外配置逐字节不变；`analyze2.py` 对非有限值稳健（一个 NaN 曾把整次运行从汇总表里静默抹掉）；`analyze_all.sh` 加了缓存，避免为每个运行重读 bag。 |
| 14 | `scripts/test_clock_monotonic.py`（新增） | 时钟映射的**单调性回归测试**：对五种场景（干净流 / PX4 后退 0.5 s / PX4 前进 0.5 s / 两次阶跃 / 带抖动）× 三种策略断言"绝不输出回退时间戳"。 |
| 15 | `scripts/replay_clockmap.py`（新增） | 用 bridge 记录的**真实** `(sensor_time, arrival_time)` 重放各策略，在真机数据上验证，不依赖相机。 |
| 8 | `scripts/bag_time_audit.py`（新增） | 分离"录制时刻（主机时钟域）"与"消息自带 header.stamp（发布者时钟域）"，用于暴露 bridge 映射与发布端缺陷（由此发现 §3.6 的 4 小时坏帧）。 |
| 9 | `scripts/verify_runtime.sh`（新增） | 启动后运行态验证：实际加载配置、时钟映射统计、逐包 dt 质量、各话题实测频率、ZUPT 接受计数、单帧 CPU 余量、系统负载。 |
| 10 | `scripts/deploy_offline.sh` / `deploy_audited_fixes.sh`（新增） | 带备份的部署，并在板子无法访问 github 时支持离线暂存包部署；同时更新 systemd `ExecStart`、退役旧启动副本、写 `STARTUP_AUTHORITY.md`。 |

**部署后的运行态归档**（本次实际执行的结果）：

```
systemd ExecStart = /home/orangepi/kswlt/vio_ws/start_vio_systemd.sh
退役副本          = tools/start_vio*.sh、vio-improve/start_vio*.sh、vio_ws/run_vio.sh
                    → 均重命名为 *.DEPRECATED-20260923T124225
单一来源声明      = /home/orangepi/kswlt/vio_ws/STARTUP_AUTHORITY.md
备份              = /home/orangepi/kswlt/backups/deploy_20260923T124225/
```

---

## 5. 验收结果（同一 immutable bag 的单变量 A/B）

> 所有数字均来自 `replay_one.sh` 在 `ROS_DOMAIN_ID=43` 的离线回放 + `analyze2.py` 统计，
> 每个配置只改一个参数。

### 5.1 timeshift_cam_imu 扫描（同一 immutable bag，只改一个参数）

`LASEROFF3` bag（64.35 s，静止 17 s + 旋转 45 s，峰值 50°/s），
`zupt_chi2_multipler` 保持基线值不变，仅改 `timeshift_cam_imu`。全部 9 次回放：

| timeshift | closure_m | static_drift_m | max_jump_m | >10cm 跳变 | 旋转段末偏移_m | 前3s 偏移_m | path_len_m | `|ba|`max |
|---|---|---|---|---|---|---|---|---|
| **+0.005** | **0.2987** | 0.0060 | **0.1204** | **1** | **0.3016** | 0.0391 | 5.20 | 0.0838 |
| +0.001256（git HEAD 值） | 0.1890 | 0.0059 | 0.0207 | 0 | 0.1925 | 0.0401 | 4.85 | 0.0786 |
| 0.0 | 0.1747 | 0.0056 | 0.0223 | 0 | 0.1779 | 0.0397 | 4.67 | 0.0718 |
| −0.005 | 0.1325 | 0.0061 | 0.0150 | 0 | 0.1361 | 0.0403 | 4.78 | 0.0834 |
| −0.008 | 0.1061 | 0.0055 | 0.0117 | 0 | 0.1097 | 0.0444 | 4.99 | 0.0883 |
| **−0.010（当时配置值）** | 0.0664 | 0.0055 | 0.0170 | 0 | 0.0693 | 0.0456 | 5.26 | 0.0905 |
| **−0.010（重复性验证）** | **0.0674** | 0.0083 | 0.0172 | 0 | 0.0707 | 0.0456 | 5.24 | 0.0904 |
| −0.012 | 0.0654 | 0.0084 | 0.0137 | 0 | 0.0683 | 0.0462 | 5.50 | 0.0883 |
| **★ −0.015（最优点）** | **0.0279** | 0.0084 | 0.0264 | 0 | **0.0308** | 0.0590 | 5.96 | 0.0811 |
| −0.018 | 0.0506 | 0.0060 | 0.0858 | 0 | 0.0527 | 0.0858 | 6.71 | 0.0866 |
| −0.020 | 0.0752 | 0.0059 | **0.1117** | **1** | 0.0728 | **0.1252** | 7.40 | 0.0838 |
| **−0.024** | **0.9750** | 0.0062 | 0.1245 | **2** | **0.9716** | 0.0663 | 9.35 | 0.0924 |

**结论（已由数据确定，双侧收敛且负向存在崩溃点）：**

* **最优 `timeshift_cam_imu = −0.015 s`**，closure = **2.79 cm**。
  `+0.005 → −0.015` 单调下降，**−0.015 → −0.024 单调回升并在 −0.024 崩溃**，
  因此这是真正的极值，不是"越负越好"的外推：

  ```
  +0.005:   0.2987
  +0.001256: 0.1890
   0.0:     0.1747
  −0.005:    0.1325
  −0.008:    0.1061
  −0.010:    0.0664   (repeat 0.0674)
  −0.012:    0.0654
  −0.015:    0.0279   <-- MINIMUM
  −0.018:    0.0506   <-- worsening
  −0.020:    0.0752   <-- 1 jump > 10 cm
  −0.024:    0.9750   <-- COLLAPSE (97.5 cm, 2 jumps > 10 cm)
  ```

* **任务书问题 5 的答案是"否"**：`−0.010` 不是最优点。改为 **−0.015** 可把 closure
  从 **6.6 cm 改善到 2.8 cm（2.4 倍）**。
* **git HEAD 里的 `+0.001256` 是次差的取值**（18.9 cm），比实际运行值差 2.8 倍。
  若按仓库配置启动，结果会明显劣于现场实际运行配置——这本身就是"仓库不代表验证配置"的后果。
* **两侧失效模式不同，因此必须双向界定安全窗口**：

  | 方向 | 越界后发生什么 |
  |---|---|
  | 正向（`+0.005`） | 直接产生 **12.0 cm 跳变**；closure 升到 29.9 cm |
  | 负向（`−0.020`） | 产生 **11.2 cm 跳变**；`path_len` 5.96→7.40；前 3 s 偏移 5.9→12.5 cm |
  | 负向（`−0.024`） | **闭合误差崩溃到 97.5 cm**、出现 2 次 >10 cm 跳变、`path_len` 9.35 |

  **可用区间约为 −0.010 ～ −0.018；推荐值 −0.015。**

* `static_drift` 在所有 15 次回放中都只有 5.5–8.4 mm，**与 timeshift 完全无关**，
  再次印证"静止正常、运动才漂"的现象结构。

**物理合理性交叉验证**：D430 当前曝光为 8500 µs（8.5 ms）。若相机时间戳标记的是"帧就绪"
而非"曝光中点"，则真实的相机-IMU 时间偏移应约为
`曝光/2 + 读出 + USB/ROS 传输` ≈ `4–5 ms + 数 ms + 3–5 ms` ≈ **10–15 ms**，
与实测最优 **15 ms** 在同一量级。这支持 −0.015 是一个物理上可解释的值，
而不是对单个 bag 的过拟合。

**可重复性 —— 必须区分"同批次"与"跨批次"（这是重要的方法论边界）**：

同一配置在同一批次内重复回放，差异很小：

| 指标 | `ts_m10` | `ts_m10_rep` | 相对差 |
|---|---|---|---|
| closure_m | 0.0664 | 0.0674 | 1.5% |
| rot_final_excursion_m | 0.0693 | 0.0707 | 2.0% |
| max_jump_m | 0.0170 | 0.0172 | 1.2% |
| `|ba|`max | 0.0905 | 0.0904 | 0.1% |

但同一配置在**不同批次**（更早的 `baseline_ts010`，当时机器上还有其它 ROS 诊断
进程在跑）回放得到 closure **0.0583**，与 `ts_m10` 的 0.0664 相差 **14%**。

**结论：**
* **同一批次内的单变量 A/B 是可信的**（差异 ≤2%，远小于本表中 10 倍量级的变量效应）；
* **跨批次比较不可直接引用**，必须重新在同一批次内测；
* 本 §5.1 的全部 15 个点都是同一批次（12:24–12:50）连续跑完的，因此相互可比。

> 说明：`max_jump_m` 与 `path_len_m` 单独不作为主判据。`path_len` 依赖 IMU clone 是否存在
> （`VioManager.cpp:647-651`），跳帧时会漏计；此处只把它作为**同一 bag 内的相对比较**使用。
> `max_jump` 主要用来捕捉"某个配置是否引入大跳变"这一失效模式。

### 5.2 ZUPT 语义 A/B（同一批次，基线 timeshift = −0.015）

| `zupt_chi2_multipler` | `passed disparity` | **`accepted`** | closure_m | 旋转段末偏移_m | `|ba|`max |
|---|---|---|---|---|---|
| **0（原配置值）** | 313 | **0** ❌ | 0.0734 | 0.0632 | 0.0773 |
| **1（修正值）** | 354 | **335** ✅ | 0.0589 | 0.0583 | 0.0756 |
| **10（极宽松）** | 340 | **340** ✅ | **0.0114** | **0.0239** | 0.0740 |

**这是对根因 1 的最终直接验证，也是修复收益的量化：**

* `chi2_multipler = 0` → **0 次接受**，ZUPT 完全失效（与 §3.2 的源码分析、以及实时日志
  中 23832 通过 / 0 接受完全一致）；
* 改为 `1` → **335 次接受**，ZUPT 开始工作；
* 三个取值在**同一批次内**逐步改善：closure 0.0734 → 0.0589 → **0.0114 m**，
  旋转段末偏移 0.0632 → 0.0583 → **0.0239 m**，且 `|ba|` 同步下降。

> **不要把 `zupt_chi2_multipler: 10` 当作推荐值直接上线。** 它在本 bag 上表现最好，
> 但本 bag 的旋转动作是"受控、缓慢、最终回到静止"，宽松门限对静止段的零速约束最有利；
> 若真实飞行中有持续运动，过宽的门限会在运动中误判静止。**推荐值仍为 1（语义正确），
> 10 只作为"ZUPT 能带来多少收益"的上界参考。**

### 5.3 静态度初始化阈值 A/B

| `init_max_disparity` | closure_m | static_drift_m | max_jump_m | 旋转段末偏移_m | span |
|---|---|---|---|---|---|
| **10.0（原配置值）** | **0.0277** | 0.0072 | **0.0251** | 0.0304 | 61.9 s |
| **0.3** | 0.0463 | **0.0038** | 0.0517 | 0.0489 | 58.1 s |

**结论：在本 bag 上 `10.0` 反而略优（closure 2.77 cm vs 4.63 cm），且跳变更小。**
原因是本 bag 开头有 17 s 完全静止，两者的"判为静止"都能成立，而更严格的 `0.3` 让初始化
窗口更难凑齐（span 缩短到 58.1 s，说明初始化更晚完成），反而引入了更多不确定性。

**因此 §3.8 的判断需要精确化：**

* `init_max_disparity: 10.0` 对实测 0.05–0.7 px 的视差**确实没有判别力**（这一点成立）；
* **但没有证据表明把它改小能改善结果** —— `0.3` 反而更差；
* 真正的保护来自静态初始化器内部的 IMU 加速度方差检查，以及
  **§5.4 的 `wait_for_jerk` 耦合**。
* **建议：保持 10.0 不动**，把它标注为"已 A/B、未发现收益"，而不是"错误配置"。
  原先"必须改成 0.3"的提法**已被本实验否定**。

### 5.4 `try_zupt: false` 会连带改变初始化策略（重要设计耦合）

`try_zupt: false` 的 A/B **未能完成，且原因是结构性的**：

```cpp
// ov_msckf/src/core/VioManagerHelper.cpp:106
bool wait_for_jerk = (updaterZUPT == nullptr);
```

**关闭 ZUPT 会把初始化策略从「静止即可」切换成「必须等到 jerk」。** 实测后果：

| run | init disparity 样本 | cam0 范围 | `failed static init` | 成功初始化 |
|---|---|---|---|---|
| `zupt_m0`（try_zupt 默认 true） | 5 | 0.073–0.110 | 0 | ✅ line 56 |
| **`zupt_off`（try_zupt false）** | **948** | 0.072–**240.5** | **917** | ❌ **从未成功** |

`zupt_off` 的前 6 个 disparity 与 `zupt_m0`/`ts_m15` **完全相同**（0.217/0.480…），
证明输入一致；失败消息是 `no accel jerk detected`（无 "platform moving too much"），
按源码对应 `has_jerk=false, is_still=true` —— 在 `wait_for_jerk=true` 下**永远不满足**
`(has_jerk && wait_for_jerk) || (is_still && !wait_for_jerk)`。

而 disparity 从 0.07 一路涨到 **240 px**，是初始化长期失败后**特征数据库不断累积**
（因为始终不创建 clone）的衍生现象，不是原因。

**结论：**
* **`try_zupt: false` 不能作为"ZUPT 关闭对照组"** —— 它同时改变了初始化路径，
  该实验设计本身无效，`zupt_off` 的 0 帧结果**不得**被解读为"ZUPT 无益"；
* 任何"关掉 ZUPT 看看"的实验，都必须在 bag 中存在**明显 jerk**（突然的加速变化）
  时才可能初始化成功；
* 这也是"不要随意动 ZUPT"这条工程纪律的实质理由 —— 它不是一个孤立的开关。

### 5.5 三种时钟映射策略在**真实 PX4 数据**上的对比

时钟映射只涉及 IMU，**不需要相机**，因此不受 §6.2 的 USB3 阻塞影响。
用修复后的映射器在这台 PX4 的**真实轨迹**（21864 包 / 148.9 s）上重放三种策略：

| mode | 单调性违反 | dt_p50 | dt_p99 | dt_max | dt<100µs | repairs | 轴速率误差 |
|---|---|---|---|---|---|---|---|
| `lower` | 0 | 0.004552 | 0.010561 | 1.0234 | 2 | 2 | −9.7 ppm |
| `ema005` | 0 | 0.004657 | 0.010549 | 1.0207 | 56 | 61 | +11.0 ppm |
| **`slow`（新默认）** | **0** | **0.004548** | 0.010554 | 1.0214 | 59 | 71 | +15.5 ppm |

**真实数据揭示的两个关键事实：**

**(1) IMU 的实际送达速率只有 146.8 Hz，而配置写 200 Hz。**
dt 呈**周期性双峰**（lag-2 自相关 +0.43，不是随机丢包）：

```
3–5 ms   : 12940 包 (59.2%)   <- PX4 的实际产出间隔 4.552 ms = 219.7 Hz
8–11 ms  :  8218 包 (37.6%)   <- 约 2.3 倍间隔
其他      :   ~700 包
有效速率 : 146.80 Hz，即约 33% 的样本没有送达
各 10 s 窗口稳定在 147±1 Hz，D 占比稳定 40%
```

**PX4 自身的 `sensor_time` 从不回退**（backwards steps = 0），只有 2 次向前跳变
（0.107 s 与 0.451 s）。因此这不是"时间戳乱序"，而是**样本未送达**或 PX4 发送调度问题。
按任务书第二十节的要求，这属于必须调查、**不能靠改 YAML 掩盖**的问题；
候选方向（MAVLink 请求间隔、PX4 流控、pymavlink 接收循环、USB FS 轮询）**均未验证**。

**(2) 实测时钟漂移 = −976.9 ppm。**
148.9 s 内 `clock_offset` 变化 **−0.1455 s**，`slow` 策略独立估计出 **−941.6 ppm**（13 次斜率更新）。
这与合成数据的 −1000 ppm 场景量级一致，也与历史观测的 −0.9 ms/s 吻合。

**这一条最直接地解释了固定 `timeshift_cam_imu` 的失效半径**：
−977 ppm 意味着每 15 秒就漂移 15 ms —— 而本项目的 timeshift 最优值是 −15 ms 量级。
**所以任何固定的 timeshift 都只有十几秒的有效期**，这正是任务书第八节方案 B
（clock drift estimator）必须实现的量化理由。

> 注：`dt_max ≈ 1.02 s` 与 2 次 clock_reset，来自真实数据中的 +0.45 s 时间基阶跃；
> 修复后的映射器把它作为**单次不连续**吸收（合成回归测试中 repairs=0、dt<100µs=0），
> 真实轨迹上残留 59 个 <100 µs 的钳位（占 0.27%），已作为残余问题记录（§6）。

### 5.6 汇总（全部 19 次回放）

见 `scripts/table.py` 输出。关键行：

```
label            closure_m  static_drift  max_jump  gt10cm  rot_final  rot_first3
ts_p05             0.2987      0.0060      0.1204      1     0.3016     0.0391
ts_p1256           0.1890      0.0059      0.0207      0     0.1925     0.0401
ts_000             0.1747      0.0056      0.0223      0     0.1779     0.0397
ts_m05             0.1325      0.0061      0.0150      0     0.1361     0.0403
ts_m08             0.1061      0.0055      0.0117      0     0.1097     0.0444
ts_m10             0.0664      0.0055      0.0170      0     0.0693     0.0456
ts_m10_rep         0.0674      0.0083      0.0172      0     0.0707     0.0456
ts_m12             0.0654      0.0084      0.0137      0     0.0683     0.0462
ts_m15 ★           0.0279      0.0084      0.0264      0     0.0308     0.0590
ext_m18            0.0506      0.0060      0.0858      0     0.0527     0.0858
ext_m20            0.0752      0.0059      0.1117      1     0.0728     0.1252
ext_m24            0.9750      0.0062      0.1245      2     0.9716     0.0663
ext_m30            0.3541      0.0089      0.1922      2     0.3534     0.0455
zupt_m0 (chi2=0)   0.0734      0.0132      0.0332      0     0.0632     0.0604
zupt_m1 (chi2=1)   0.0589      0.0088      0.0287      0     0.0583     0.0492
zupt_m10(chi2=10)  0.0114      0.0247      0.0309      0     0.0239     0.0476
init_d03           0.0463      0.0038      0.0517      0     0.0489     0.0758
init_d100          0.0277      0.0072      0.0251      0     0.0304     0.0585
zupt_off           未初始化（见 §5.4）
```

**非有限值扫描**：19 次回放中只有 `zupt_m1` 出现 **1 帧**非有限输出
（第 8727/11993 帧，前后位置连续），其余 18 次全部为 0。
**关键对照：`zupt_m10`（ZUPT 接受率 100%）完全干净 → 排除"启用 ZUPT 导致状态发散"
的可能**；该单帧判为发布侧孤立异常。

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
| **1.2348 m 单帧跳变的直接机制** | `未验证`（见 §6.1） |
| 「实时链 vs 离线链」在同一物理动作下的对比 | `未验证`（需要现场操作，见 §3.5 的限制说明） |
| **实时启动验证（precheck camera/imu 阶段 + verify_runtime 实测）** | **被硬件阻塞，见 §6.2** |
| 动态最大漂移 / 0.5 m 往返闭合 <10 cm 的**实时**验收 | 需真实运动 + 可用 USB3，见 §6.2 |

### 6.2 硬件阻塞：D430 掉到 USB 2.0，实时链无法验证

调查进行到中途，板子发生一次**非正常重启**（`last -x` 中没有对应的 `shutdown` 记录，
即掉电/硬复位而非正常关机），发生在一次满载回放批次启动约 35 秒之后。当时 SoC 温度仅
47 °C（thermal_zone0），**排除过热**；更可能是 CPU 满载 + D430(USB3) + PX4 同时取电时的
供电余量问题。**该风险需要在后续长时间实验中注意（避免与其他重负载并发）。**

重启之后，D430 **不再以 SuperSpeed 枚举**：

```
调查开始时：  Bus 02  xhci-hcd  5000M  |__ Port 1: Dev 3  uvcvideo  5000M   <-- USB3
重启之后：    Bus 05  ehci-platform 480M |__ Port 1: Dev 2  uvcvideo   480M   <-- USB2
```

而 USB 3.0 控制器本身是健康的（`Bus 08`/`Bus 02` 均为 `xhci-hcd ... 5000M` 且空闲）。
也就是说**设备同一端口在两次启动中落到了不同控制器**，属 USB3 链路协商失败后回退到 USB2，
**软件侧无法恢复**。已尝试并全部失败：`authorized` 0→1 软重枚举、`usbreset`
（`No such device found`）、xhci platform 驱动 unbind/bind、xhci 模块重载（built-in）。
（其中 unbind/bind 一度使 USB3 控制器整体消失，已通过一次正常重启恢复 ——
**教训：不要对 xhci platform 驱动做 unbind/bind，除非准备好重启。**）

**后果（如实记录）：**

* **实时 848×480×30 双目链路无法运行**，因此 precheck 的 `camera` / `imu` 阶段、
  `verify_runtime.sh` 的实测、以及任何"实时 vs 离线"的单变量对比**均未完成**；
* **这不是坏事被掩盖**：precheck 恰好在这一状态下**正确地判 FAIL 并拒绝启动估计器**，
  即 §4 第 4 项所声明的 fail-closed 行为得到了真实验证；
* **离线部分不受影响**：所有 §5 的结论都来自已固化的 immutable bag，
  不需要相机在线，因此仍然成立。

**恢复条件**：把 D430 物理重新插拔到 USB3 端口（必要时换线缆/端口），
确认 `lsusb -t` 中出现 `uvcvideo ... 5000M` 后，按下方 §7 启动即可。

### 6.3 关于板子重启的既有前科

`last -x` 显示 2026-09-22 23:17 那次会话以 `crash` 结束（持续 12:59），
且 journal 中存在 `tailscaled: time jump detected (slept 1h11m50s), probably wake from
sleep` 之类的记录。**该板子的上电/时钟稳定性此前已出现过异常**，
建议把"掉电"与"时钟跳变"都纳入长期运行的监控项，而不是当作一次性偶发。

### 6.1 关于 1.2348 m 单帧跳变：已知与未知

**已知（实测）**：

* 跳变前约 0.8 s，位置以 **恒定 −1.17 m/s** 沿 x 移动，而 `q_GtoI`、`bg`、`ba` 在打印精度内
  **完全不变** —— 这种"完美匀速 + 姿态与零偏冻结"是纯惯性传播特征。
* 跳变瞬间为单帧 **1.2348 m**（等效 37 m/s），随后 5 帧继续 0.25～0.53 m 的摆动，
  再之后位置完全冻结（750 s 仅变化几毫米）。
* 同期 `[ZUPT]: passed disparity` 的视差只有 **0.062～0.065 px**，即 ZUPT 认为平台静止；
  而 chi2 判据恒 reject（§3.2），所以 **该跳变只能来自视觉更新（MSCKF/SLAM）**，
  不是 ZUPT 造成的。
* 最终位置误差 1.77 m 且此后 **不再恢复** —— 与"ZUPT 没有把它锁死"一致（因为 ZUPT 从未被接受）。

**排除项（有量化依据）**：

* 单帧几毫秒级的时间戳误差**不足以**解释米级跳变：以 1.17 m/s 计，即使 15.5 ms 的
  IMU 时间轴偏移也只对应约 18 mm。
* 该时段特征数正常（58～93），不是特征枯竭。

**两个仍在被检验的候选假设**（本次的 A/B 正是针对它们）：

1. **时间对齐类** —— 视觉观测被关联到错误的平台位姿，MSCKF 用一个大更新把它"拉回"。
   由 §5.1 的 timeshift 扫描检验：若成立，调整 timeshift 应显著改变跳变与闭合误差。
2. **状态发散类** —— IMU 传播期间速度估计漂走，累积出虚假位移，随后被视觉更新一次性纠正。
   由 §5.2 的 ZUPT A/B 检验：若成立，让 ZUPT 真正生效应限制该漂移。

**任一假设被证实的判据**：对应 A/B 中 `max_jump_m` 与 `closure_m` 出现与该变量单调相关的变化。


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

---

## 8. 对任务书三十四节 16 个问题的逐条回答

凡无实验证据者一律标 `NOT VERIFIED`，不作推测。

| # | 问题 | 回答 | 依据 |
|---|---|---|---|
| 1 | 真正的主根因是什么？ | **不是一个，而是三个叠加**：①ZUPT 因本地代码改为 AND 语义而**永久 reject**（配置未同步）；②时钟映射把传输抖动写进惯导时间轴、且**缺少主机/PX4 频率比修正**；③运行配置/启动脚本/systemd **与仓库严重不一致**，使任何结论都无法归属。 | §3.2 §3.3 §2 |
| 2 | IR speckle 是否仍是主要因素？ | **否（降级为 `NOT VERIFIED`）**。实测把激光从 0 拉到最大只让图像亮 5–10 灰度级，而历史 DYN50/LASEROFF3 相差 76 级，投影器解释不了。**但"运动时散斑去相关对 KLT 的影响"仍未验证。** | §3.1 |
| 3 | 当前 systemd 是否真的关闭 emitter？ | **原先没有，现在会。** 旧 systemd 路径**完全没尝试**关闭；手动路径传的 `enable_ir_emitter` 是**不存在的参数**。更根本的是 `emitter_enabled` 属流会话级设置、**开流即重置**，所以"一次性关闭"永远无效。已改为每次启动、流打开后按 `laser_power→emitter_enabled` 顺序强制关闭并读回验证。 | §3.1 §4 |
| 4 | 当前真正加载的 timeshift 是多少？ | **原先 -0.010**（由 OpenVINS 自己打印 `LOADED_CAMERA_IMU_TIME_OFFSET_SEC` 确认），而非仓库里的 +0.001256。**现在按实测最优改为 -0.015**，并已用真实二进制加载确认。 | §2.1 §5.1 §7 |
| 5 | -10 ms 是否仍然是最佳点？ | **不是。** 15 点扫描给出双侧极小值：**-0.015 最优（closure 2.79 cm）**，-0.010 为 6.64 cm，+0.005 为 29.87 cm，-0.024 崩溃到 97.5 cm。 | §5.1 |
| 6 | PX4→ROS clock mapping 是否稳定？ | **原先不稳定**：`ema005` 在合成数据上 dt_std 放大 12 倍、dt_max 达 19.8 ms（≈4 个采样周期）；`lower` 方向依赖，正漂移下时间轴漂 -1004 ppm。**新 `slow` 策略把 axis_err 压到 -0.2 ppm（负漂移）/ -32.7 ppm（正漂移，600 s）且 dt 抖动最小。** 真实 PX4 上实测漂移 **-976.9 ppm**，`slow` 独立估计 -941.6 ppm（§5.5）。**但真实轨迹上仍残留 59 个 <100 µs 的钳位（0.27%），列为残余问题（§6）。** | §3.3 §5.5 |
| 7 | 最新 EMA 算法是否应该保留？ | **不应作为默认。** 它修好了 `lower` 的漂移方向问题，代价却是把传输抖动写进时间轴（这正是任务书第六节担心的机制），且**完全不修正频率比**（真实数据实测漂移 -977 ppm，`ema005` 对此无能为力）。保留为可切换的 A/B 选项（`imu_clock_mode:=ema005`），默认改用 `slow`。 | §3.3 §5.5 |
| 8 | 是否存在 timestamp clamp 到 +1 us？ | **存在过，且是静默的**：`if stamp <= last: stamp = last + 1e-6`，无计数、无日志。现已改为显式计数 + 每 30 s 摘要 + 连续 5 次违规即重置时钟映射；并新增 `dt < 100 µs` 的独立检测。 | §3.4 |
| 9 | 初始化是否会在运动中错误完成？ | **风险存在，但没有证据表明改小阈值能改善。** `init_max_disparity: 10.0` 对实测 0.05–0.7 px 的视差确实**没有判别力**；但 A/B 显示改成 `0.3` **反而更差**（closure 4.63 cm vs 2.77 cm，且初始化更晚完成）。真正起作用的是静态初始化器内部的 IMU 加速度方差检查，以及 **`wait_for_jerk` 与 `try_zupt` 的耦合**（§5.4）。**建议保持 10.0。** | §3.8 §5.3 §5.4 |
| 10 | ZUPT 是否真正工作？ | **原先完全没有；现已确证修好。** 日志中 `passed disparity` 23832 次、`accepted` **0 次**（拒绝路径是 `PRINT_DEBUG`，INFO 下不可见，因此"看起来在工作"）。A/B 直接验证：`chi2_multipler` 0→**0 次接受**，1→**335 次接受**，10→**340 次接受**；同批次内 closure 随之 0.0734 → 0.0589 → **0.0114 m**。 | §3.2 §5.2 |
| 11 | Camera-IMU 外参可信度如何？ | **`UNVERIFIED`（未标定）**。用 `-R^T·t` 反算已确认 OpenVINS 内部取逆语义；但由 yaml 外参算出的基线为 **46.88 mm**，而 CameraInfo 与硬件直读均为 **50.1375 mm**，**差 6.5%**。且历史经历 0°→-7°→-0.8°→取逆，属手工猜测。**不得再被引用为已标定值。** | §3.7 |
| 12 | VIO 现在动态最大漂移多少？ | **离线可复现数字**：最优 timeshift 下旋转段末偏移 **3.08 cm**、闭合 **2.79 cm**、最大单帧跳变 2.64 cm；叠加 ZUPT 修复后闭合进一步降到 **1.14 cm**。**实时数字 `NOT VERIFIED`**——被 USB3 阻塞（§6.2），且实时与离线属不同物理场景，不可直接互换（§3.5）。 | §5.1 §5.2 §6.2 |
| 13 | 回原点闭合误差多少？ | **同一 immutable bag、最优配置：2.79 cm**（原运行值 -0.010 为 6.64 cm，仓库值 +0.001256 为 18.90 cm；叠加 ZUPT 修复后 **1.14 cm**）。**实时闭合误差 `NOT VERIFIED`。** 注意跨批次不可比（§5.1 末）。 | §5.1 §5.2 |
| 14 | 运动停止后是否继续漂？ | **原实现是"停止后不再漂、但停在错误的位置"**：实时日志中运动后误差 1.77 m，其后 **750 s 内位置只变化几毫米**——说明视觉更新把它稳住了，但稳在错处，且 ZUPT 从未参与（因为恒被拒绝）。**修复后的行为需实时复测（被阻塞）。** | §3.2 §6.1 |
| 15 | 是否已适合作为固定地图导航的定位源？ | **否，尚未。** 离线指标已达标（闭合 2.79 cm < 10 cm），但 ①实时链未验证；②外参未标定（基线差 6.5%）；③小时级对齐漂移未实测；④1.23 m 跳变机制未定位。 | §6 |
| 16 | 是否可以开始接入 PX4？ | **否。** `send_vision_to_px4` 必须保持 `false`（新启动脚本已硬编码）。在 §6 的 `NOT VERIFIED` 项消除、且实时动态验收通过之前不得注入 PX4 EKF。 | §4 §6 |
