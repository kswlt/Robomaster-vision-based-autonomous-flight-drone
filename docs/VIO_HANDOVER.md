# D430 双目 + PX4 IMU + OpenVINS —— 交接文档（实机测试用）

```
交接 HEAD   : 见文末「Git 状态」（本次改动尚未全部提交）
交接日期    : 2026-09-23
运行环境    : Orange Pi 5 (RK3588) / ROS 2 Humble / ROS_DOMAIN_ID=42 / ROS_LOCALHOST_ONLY=1
运行时目录  : /home/orangepi/kswlt/vio_ws
```

本文件只写**当前实测能证明的东西**。凡是没有实测支撑的，一律标 `尚未验证`。

---

## 0. 一句话结论

启动链已统一并 fail-closed；ZUPT 的致命配置错误已修（实测 `accepted` 从 **0 → 1916/1916**）；
PX4→ROS 时钟映射已换成可审计实现；双目外参的 6.5% 基线错误已按设备自带 CameraInfo 修正。

**本轮实机静止验收已通过**：静止 120 s 净漂移 **0.8 mm**，单帧最大跳变 **0.4 mm**，
非有限值 **0**，超时比例 **70.2% → 0.1%**（详见 §1.6）。

**但"移动/平移/旋转后的漂移"仍未验收** —— 这正是当初要解决的问题，也是唯一还没验的关键项。
§4.3 就是给这次动态验收用的步骤。

---

## 1. 已确认并修复的问题（每条都有实测证据）

### 1.1 ZUPT 被配置成永久失效（致命）

**证据**：运行中的源码树
`vio_ws/src/open_vins/ov_msckf/src/update/UpdaterZeroVelocity.cpp`
（sha256 `d7858e493d848366ad75e61475b337732ae893fedaf3e2c99f71f18cd939ff66`，
与仓库内 vendored 副本哈希一致；install 里的二进制 `2026-09-14 13:38:13` 晚于源码
`2026-09-13 16:49:24`，即跑的就是这份源码）：

```cpp
const double chi2_limit  = _options.chi2_multipler * chi2_check;
const bool inertial_passed = (chi2 <= chi2_limit);
if (!disparity_passed || !inertial_passed) { ... return false; }   // 与上游的 OR 不同
```

运行时配置曾是 `zupt_chi2_multipler: 0` → `chi2_limit = 0` → 除非 chi2 恰好为 0，否则
**永远拒绝**。而拒绝路径是 `PRINT_DEBUG`，INFO 级日志里**只看到成功的前半句**：

- 修复前实测：`passed disparity` 23832 次，`accepted` **0** 次。

**修复**：`zupt_chi2_multipler: 1`（回到上游语义：门槛 = chi2 分布的 95% 分位）。

**同批次单变量 A/B**（同一 bag、同一 timeshift −0.015、flock 串行）：

| chi2_multipler | accepted | 闭合误差 closure |
|---|---|---|
| 0（原值） | 0 | 0.0734 m |
| 1（已采用） | 335 | 0.0589 m |
| 10 | 340 | 0.0114 m |

**chi2 = 10 没有被采用**：它只是把"IMU 与视觉必须一致"这道安全网拆掉（虽然还有 15 帧
连续确认的保护），属于把门放开让指标变好看的调参，不是根因修复。

### 1.2 PX4→ROS 时钟映射：时间轴速率误差 −1000 ppm 级

**证据**：真实 PX4 数据流 21864 包 / 148.9 s，用 `arrival_offset = t_ros − t_px4` 做
稳健回归，**实测时间轴漂移 −976.9 ppm**（约 3.5 s/小时）。

**修复**：新增 `imu_clock_mapper.py`，三种策略可切换：
- `lower`（取到达偏移的下包络）：合成数据 dt_std 2.58e-5 很漂亮，
  但时间轴速率误差 **−1004 ppm**
- `ema005`：dt_std 3.23e-4，dt 最大 19.8 ms
- `slow`（**已采用**）：滑窗 P5 偏移 + 长窗稳健回归频率比。
  合成数据时间轴误差 −0.2 ppm（负漂移）/ −32.7 ppm（正漂移），抖动最小；
  真实 trace 上估到 −941.6 ppm（真值 −976.9）

回归测试还抓出并修好了我自己实现里的 4 个 bug：`reset()` 丢单调性、`reset()` 清零
计数器掩盖了一次致命 reset、前向时间基台阶被"对抗"而不是"吸收"、`reset()` 后
`bootstrapped=False` 导致新锚点被 P5 分位覆盖。

### 1.3 启动链不唯一、运行时配置不在 git 里

**证据**：运行时配置目录不是 git 仓库、堆了 8 个手工 `.bak`；systemd 实际执行的是
`tools/start_vio_systemd.sh`（在 git 里根本不存在）；现场有 5 个 `start_vio*` 变体、
4 个 `vio_bridge_combined.py` 变体；启动脚本里传的 `enable_ir_emitter` 这个参数在
本版 realsense-ros 里**并不存在**。

**修复**：`start_vio.sh` 成为**唯一权威入口**，6 个阶段 fail-closed：
配置哈希 → 硬件预检 → 强制关投影器并回读 → 相机预检 → 桥接 → IMU 预检 → OpenVINS。
`start_vio_systemd.sh` 退化成薄包装，只剩 flock 和故障闩锁。

### 1.4 双目外参基线错 6.5%（本轮新发现）

**证据（来自 bag 自带的 CameraInfo，不是推测）**：

```
infra1 / infra2 整流后：K/P 完全相同  fx=422.216248  cx=423.230835  cy=240.207138
                       distortion plumb_bob, d = [0,0,0,0,0]      （两路都是）
infra1 P[3] =   0.000000
infra2 P[3] = -21.168875   -> 真实基线 = -P[3]/fx = 50.137518 mm
```

50.137518 mm 同时就是 D430 出厂基线（SDK 报 `Stereo Baseline 50.137516`）。
畸变全 0 + 两路 K/P 只差一个 `P[3]` ⇒ **整流后的双目几何就是 `R=I, t=(−B,0,0)`**。

而 YAML 里：

```
YAML 内参          = 422.216200 423.230800 240.207100   （与 CameraInfo 差 < 5e-5 像素）
                     -> 内参是从本机抄的
YAML T_cam1_cam0   = inv(T_imu_cam1) · T_imu_cam0
                   -> |t| = 46.879 mm，残余相对旋转 0.147°    -> 差 6.50%
```

估计器启动打印也印证（旧配置）：

```
LOADED_CAMERA_0_INTRINSICS= ... P_IinC= 0.0222792  0.0226863 -0.076766
LOADED_CAMERA_1_INTRINSICS= ... P_IinC=-0.0246902  0.0224388 -0.0779234
-> |P_IinC1 − P_IinC0| = 46.98 mm
```

**后果**：三角化深度 `z_est = fx·B_yaml/d = 0.937·z_true`，每个视觉量测都带 6.3% 的
**系统性尺度偏差**。这类尺度和零偏一样，静止时完全看不出来，一动就变现。

**修复**：`kalibr_imucam_chain.yaml` 换成 `rect50` 变体（`R=I`、基线 50.137563 mm）。
**cam0 完全没有动**，所以 IMU↔cam0 这个谁也没独立标定过的外参没有被"猜"。
预检里加了强制校验：反推基线偏离 50.137518 mm 超过 1% 直接 fail。

> `尚未验证`：这个修正对**动态漂移的贡献有多大**。原计划做离线 A/B，因为你要求停
> bag 回放、直接上实机，所以改用实机 A/B：见 §4.3。

### 1.5 预检自身的两个策略缺陷（本轮修）

1. `laser_power` 是**掉电保持**的 NV 选项，而 hw 阶段原来只报错不修 → 只要有人动过
   投影器，整条链**永久卡死**。今天实测就撞上了：`laser_power = 150.0` → 拒绝启动。
   已改成自己写 0 并回读，读回不是 0 才 fail（实测输出：
   `laser_power was 150.0 -> forced to 0, read back 0 (persists)`）。
2. IMU 速率原来硬 fail 在 180 Hz。实测这是 **PX4 侧改不动的上限**（见 §2），硬 fail
   等于永久阻塞启动。已改成：< 100 Hz 才 fail（链路真坏），100–190 Hz 给出带**完整
   实测原因**的 warn。

另外修了两处小 bug：预检把带引号的配置值当字符串比导致永远误报 warn；`/imu` 检查新增
dt p95、> 20 ms 长间隔、时间戳非单调、< 100 µs 微 dt 四项。

### 1.6 实机静止验收：本轮干净环境实测（2026-09-23 16:01–16:03）

**条件**：外部脚本已全部清除（见 §3），`start_vio.sh` 六个阶段全过，配置为
`rect50 + zupt_chi2_multipler 1 + timeshift −0.015`，设备**全程静止无人触碰**，测量窗口 120 s。

**启动链**：硬件预检 PASS → 相机预检 PASS（21 项全 OK）→ IMU 预检 PASS（1 项 warn，见 §2）
→ **初始化成功**（`[init]: successful initialization in 0.0012 seconds`）。

**修复前后对照（同一条链、同一台机器）**：

| 指标 | 修复前（旧链） | 本轮实测 | 说明 |
|---|---|---|---|
| ZUPT `passed disparity` / `accepted` | 23832 / **0** | 1916 / **1916** | 根因 1 已消除 |
| 静止 120 s **净位移** | — | **0.0008 m (0.8 mm)** | 这是最有意义的数 |
| 静止单帧最大跳变 | 1.2348 m（t≈80 s） | **0.0004 m (0.4 mm)** | 无 >10 cm 跳变 |
| `/odomimu` 非有限值 | 有（曾致整表 NaN） | **0** | |
| 单帧 CPU p50 | 0.0371 s | **0.0192 s** | 快 1.9 倍 |
| 超 33.3 ms 预算比例 | 70.2% | **0.1%** | |
| 双目同步 | — | **p50 = 0 µs，max = 0 µs** | 3587 对全同步 |
| `/infra1` `/infra2` 速率 | — | **29.88 / 29.99 Hz** | 无丢帧（>50 ms 占 0.36% / 0%） |
| `/imu` 速率 | — | **148.04 Hz** | PX4 侧上限，见 §2 |
| `/imu` 时间戳非单调 / 微 dt / 重复 | — | **0 / 0 / 0** | |
| `/imu` 最大间隔 | — | **15.0 ms** | 无长空洞 |

**这一轮同时验证了 §1.4 的外参修正能正常加载运行**：估计器打印的 cam0 与 cam1
`EXTRINSICS_Q_ItoC` 四元数已经**完全一致**（整流后相对旋转为 0），这正是 `rect50` 应有的表现。

> 注意：以上是**静止**验收。**平移/旋转下的动态漂移仍未验收**，见 §6。

### 1.7 后续静止链路复核（2026-09-23 16:22）

交接后从工作站只读检查板端运行状态：相机、桥接、OpenVINS 各 1 个进程；未发现
正在运行的 sweep/replay 污染进程。运行中的桥接仍明确为
`send_vision_to_px4:=false`。10 s 实时测量结果：

- `/imu` 148.72 Hz，时间戳非单调 / 微 dt / 重复 = 0 / 0 / 0，最大间隔 10.553 ms；
- infra1/infra2 29.89 / 29.99 Hz，双目同步 p50/max = 0 / 0 µs；
- `/odomimu` 148.83 Hz，非有限值 0，最大单帧步长 0.3 mm，无 >10 cm 跳变；
- 10 s 首末位移 0.1 mm，累计路径 72.3 mm。

证据文件在板端 `/tmp/vio/phase_current_check.json`。这只是当前静止窗口复核，不能替代
平移/旋转动态验收，也不构成 PX4 视觉回传或飞行放行依据。

### 1.8 地面三阶段动态采样（2026-09-23 16:24 左右）

按 §4.3 在 PX4 视觉输出关闭时完成三个实时采样。所有阶段 `/odomimu` 非有限值均为 0，
>10 cm / >50 cm / >1 m 单帧跳变均为 0；IMU 非单调、微 dt、重复时间戳均为 0；双目
最近时间差 p50/max 均为 0 µs。但累计路径长度异常偏大：

| 阶段 | 窗口 | `/odomimu` 路径 | 首末位移 | 最大单帧步长 |
|---|---:|---:|---:|---:|
| 静止 | 60 s | 1.8298 m | 5.8 mm | 2.5 mm |
| 平移往返 | 30 s | 0.6582 m | 0.8 mm | 2.1 mm |
| 偏航往返 | 30 s | 0.6293 m | 0.6 mm | 1.4 mm |

原始 JSON：板端 `/tmp/vio/phase_static.json`、`phase_translate.json`、
`phase_rotate.json`。这次采样工具只保留累计路径和窗口首末位移，没有保留窗口内最大
位置偏移或偏航变化，因此无法证明回原位前曾正确跟踪了测试动作。静止段 1.83 m 路径
也明显不符合“厘米量级”验收目标。判定：**动态验收未通过/未充分量测，禁止放飞**；
需先查清静止路径噪声，并增强动态记录以捕获全过程位姿。`send_vision_to_px4` 仍为 false。

### 1.9 过程位姿复核与动态动作识别（16:26 后）

累计路径会把每帧亚毫米噪声累加，故补充过程最大偏移审计器
`scripts/odom_motion_audit.py`。20 s 静止采样得到：最大离开起点 **1.20 mm**、最大
单步 0.82 mm、偏航峰值变化 0.020°、报告速度 p95 0.0101 m/s、非有限值 0。这表示
此前累计路径值不能单独用于判定静止漂移。

增强审计器对随后一个标记为“30 cm 平移往返”的 30 s 窗口只测到最大位置变化 **0.71 mm**、
最大偏航变化 0.019°。所以这次记录没有显示测试动作；尚待操作者确认是否实际移动了
设备。若确实移动，则是 VIO 未跟踪动作；若未移动，需重新按动作测量。**动态验收仍未通过，
不得放飞。** 板端桥接和估计器进程仍各一个，桥接日志确认 PX4 视觉输出关闭。

### 1.10 `/odomimu` 动态发散复核与保护补丁（本轮后续）

操作者反馈手持晃动时轨迹明显飘走。随后 `/odomimu` 审计出现致命发散：30 s 内路径和
首末位移均约 **3518 m**，单步中位数 **0.566 m**、p95 **1.33 m**，速度中位数 **117 m/s**，
位置协方差 p95 **1.62×10⁸ m²**，>10 cm 跳变 **4461 次**。同时 OpenVINS 日志里的
`p_IinG` 仍在约 0.1–0.2 m；这提示异常集中在 IMU 回调发布的快速传播 `/odomimu`，但根因
仍需运行新构建后验证。

源码检查发现 `Propagator::fast_state_propagate()` 未验证请求时间必须晚于缓存状态时间；
相机更新与 IMU 回调并发时，反向/过期区间可能被送入积分。已加 fail-closed 保护：拒绝
非有限、非正向或超过 100 ms 的传播区间，并拒绝非递增、单段超过 20 ms 或不足两条的
IMU 样本序列。该保护补丁**尚未完成链接及实机验证**，不能当作发散问题已经修复。

为避免继续发布异常里程计，板端 VIO 估计器已停止；Foxglove bridge 保持运行并限制为
低负载话题 `/poseimu`、`/tf_static`。`send_vision_to_px4` 仍保持 **false**。当前禁止飞行；
需先完成新构建、地面静止/手持动态复核，并确认 pose 轨迹稳定后再评估后续步骤。

---

## 2. IMU 速率：实测 145 Hz，是 PX4 侧的上限（未解决）

你要求 PX4 IMU ~195–200 Hz。**实测 145–154 Hz**，结论是：不是我们丢包，也不是带宽，
是 PX4 自己定的。

**证据 1 — MAVLink `seq` 完全连续**：
桥接自己记的诊断 CSV（`/tmp/vio/imu_clock_diag_*.csv`）里 seq 相邻差 1999 个全部 = 1，
**跳号 0 次，丢失率 0.00%** → PX4 就只发了这么多。

**证据 2 — 四种办法全部无效**（板子上逐项对照，每项 8–10 s）：

| 操作 | HIGHRES_IMU 实得 |
|---|---|
| 现状 | 152.1 Hz |
| `SET_MESSAGE_INTERVAL(234, 5000 µs)` = 200 Hz | 145.8 Hz |
| `SET_MESSAGE_INTERVAL(234, 2500 µs)` = 400 Hz | 145.1 Hz |
| `SET_MESSAGE_INTERVAL(234, 1000 µs)` = 1000 Hz | 145.7 Hz |
| `RAW_SENSORS` 流请求 100 Hz | 145.1 Hz |
| `RAW_SENSORS` 流请求 400 Hz | 145.4 Hz |
| ATTITUDE 压到 1 Hz | 147.0 Hz |
| ATTITUDE + ODOMETRY 压到 1 Hz | 149.2 Hz |
| **所有 ≥10 Hz 的流全压到 1 Hz（总消息 469 → 241 /s）** | **154.3 Hz** |

`GET_MESSAGE_INTERVAL` 对 msgid 234 返回 `interval_us = -1`，说明 HIGHRES_IMU 不是按
逐消息间隔发的，而是被流/档位预置固定住的。

**证据 3 — PX4 参数**（pymavlink 会把 INT32 参数按 float 解，下面是位模式还原后的真值）：
`MAV_0_CONFIG=101`(TELEM1@115200)、`MAV_0_RATE=4000`、`MAV_0_MODE=0`(Normal)、
`MAV_1_CONFIG=103`(TELEM2@921600)、`MAV_1_RATE=0`、`IMU_INTEG_RATE=200`、
`IMU_GYRO_RATEMAX=800`。总带宽只有 29 kB/s，远没到链路限制。

**结论与代价**：145 Hz 是 USB MAVLink 实例走 Normal 档位预置流的固有速率，**伴飞机侧
改不动**。OpenVINS 在 145 Hz 上能正常工作，代价是传播步长变粗（实测 sensor dt
p50 = 4.55 ms、p95 = 10.56 ms，并且是双峰的）。如果要真正拿到 200 Hz，需要改飞控侧
（把对应 MAVLink 实例的模式改成 Onboard 之类）并重启飞控——**属于飞控改动，本轮没做**。

> `尚未验证`：改飞控 MAVLink 实例模式后能否真的到 200 Hz。

---

## 3. 外部污染源（重要，实测前必查）

这板子上会反复出现**不是我建的**自动化脚本，它们会直接破坏测量有效性：

| 脚本 | 首次出现 | 它干了什么 |
|---|---|---|
| `/tmp/sweep_realts.sh` | 15:20:57 | `sed` 改运行时 `estimator_config.yaml`，起估计器，播 `realts_bag` |
| `/tmp/sweep2.sh` | 15:56:41 | 同上，另加 `pkill -9 -f "install/ov_msckf"` |
| `/tmp/launch2.sh` | 15:56:41 | 拉起 `sweep2.sh` |

**致命的一点**：它们里面的 `pkill -9 -f "install/ov_msckf"` **正好匹配我们自己估计器的
二进制路径** `/home/orangepi/kswlt/vio_ws/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf`，
所以我们的估计器会被反复杀掉。今天 15:58 那一轮初始化失败（`[init-s]: unable to select
window of IMU readings, not enough readings`）就是被它杀的——IMU 缓冲永远攒不满。
**这不是配置问题。**

**实测前必查**（三条，10 秒）：

```bash
pgrep -af 'sweep|launch2|replay_one|crossbag'          # 应为空
ls -lt --time-style=+%H:%M /tmp/*.sh | head            # 看有没有新出现的脚本
ps -eo pid,args | grep -E 'run_subscribe_msckf' | grep -v grep   # 只应有 1 个
```

如果用户侧确实有另一个自动化会话在跑，**必须让它停**，否则任何实机验证都无效
（两个估计器抢同一个域、配置还会被 `sed` 改掉）。

---

## 4. 实机操作手册

### 4.1 启动 / 停止

```bash
# 启动（唯一权威入口）。加 --foxglove 可开可视化，但它约占 40% CPU，
# 测量时建议关掉，让估计器数据通路独占
bash ~/kswlt/vio_ws/start_vio.sh -d 42
bash ~/kswlt/vio_ws/start_vio.sh -d 42 --foxglove

# 停止
#   前台运行时 Ctrl-C 即可；后台运行时：
bash /tmp/live_validate.sh stop
```

启动链会依次打印所有会影响估计结果的文件的 SHA256、实际加载的
`LOADED_CAMERA_IMU_TIME_OFFSET_SEC`、以及**反推出来的双目实际基线**。
**每一轮验收都要留这份日志。**

### 4.2 关键量测脚注

```bash
# 单独跑预检
python3 ~/kswlt/vio_ws/scripts/vio_precheck.py {hw|camera|imu|all} \
        ~/kswlt/vio_ws/src/open_vins/config/d430 42

# 看/切双目外参（只用这一条命令切，不要手改文件）
bash ~/kswlt/vio_ws/scripts/set_extrinsics.sh show
bash ~/kswlt/vio_ws/scripts/set_extrinsics.sh rect50        # 真实整流几何（当前默认）
bash ~/kswlt/vio_ws/scripts/set_extrinsics.sh baseline46    # 回到原来那个错的

# 实时链路测量（帧率、丢帧、双目同步、单帧跳变、非有限值）
python3 /tmp/live_timing.py 60 /tmp/vio/phase_<名称>.json

# IMU 侧取证（seq 连续性 / 真实速率 / 时钟映射状态）
python3 /tmp/s_imu_audit.py /tmp/vio/imu_clock_diag_<时间戳>.csv
```

### 4.3 实测步骤（这就是"动态漂移"验收）

初始化是**静态初始化**（`init_dyn_use = false`），所以：

```
0) 起链条前先做 §3 的三条污染检查
1) 启动 → 保持相机 COMPLETELY STILL，等日志出现 successful initialization
   （不要去晃、不要去挥）
2) 静止段：不动 60 s
     python3 /tmp/live_timing.py 60 /tmp/vio/phase_static.json
3) 平移段：缓慢平移约 30 cm，再缓慢回到原位，然后不动 30 s
     python3 /tmp/live_timing.py 30 /tmp/vio/phase_translate.json
4) 旋转段：绕竖直轴缓慢转约 90°，再转回原位，然后不动 30 s
     python3 /tmp/live_timing.py 30 /tmp/vio/phase_rotate.json
```

**验收判据**（`/odomimu` 是权威，`/odomimu_viz` 只用于可视化，绝不用于控制/建图）：

| 阶段 | 看什么 | 期望 |
|---|---|---|
| 静止 60 s | `path_len` / `n_jumps_10cm` | 路径长度应在厘米量级；**不允许出现 > 10 cm 的单帧跳变** |
| 平移回原位 | `displacement` | 回到起点附近的误差应为厘米量级 |
| 旋转回原位 | `displacement` | 同上；历史故障是这里出现 1.2 m 级单帧跳变 |
| 全程 | `n_nonfinite` | 必须为 0 |
| 全程 | `/imu` dt 分布 | 非单调 0、微 dt 0；p95 ≈ 10.5 ms 属正常（PX4 侧） |

### 4.4 外参实机 A/B（如果你想验证 §1.4 值多少）

```
先跑一遍   set_extrinsics.sh rect50     → 走完 §4.3 → 记下三个阶段的数字
关掉链条   set_extrinsics.sh baseline46 → 起链条 → 走完 §4.3 → 再记一遍
跑完务必   set_extrinsics.sh rect50     （或者按结论定下来）
```
切换脚本会自动把当前文件备份到 `~/kswlt/backups/kalibr_imucam_chain.before_<模式>_<时间戳>.yaml`。

---

## 5. 明令禁止 / 红线

- **`send_vision_to_px4` 必须保持 `false`**，直到底盘/飞控侧的 VIO 动态验收通过。
  它现在硬编码在 `start_vio.sh` 里。
- 不要在 VIO 验收通过前开始建图 / A\* / 轨迹规划 / PX4 控制。
- **不要用 bag 回放去替代实机验收**（离线回放只能做单变量对照，不能代表实机时序）。
- 不要手改运行时配置里的文件来"试一下"——所有切换都走
  `scripts/set_extrinsics.sh`，其它改动走 git 并记哈希。
- 不要一次改多个参数。所有已做的结论都是**同批次单变量**对照。

---

## 6. `尚未验证` 清单（不要当成已完成）

1. **平移 / 旋转下的动态漂移** —— 这是本次要解决的核心问题，也是唯一**还没验收**的关键项。
   本轮只做了静止 120 s（结果见 §1.6：净漂移 0.8 mm、无跳变）。
   实机动态验收步骤见 §4.3。
2. **外参修正（基线 46.88 → 50.14 mm）对动态精度的贡献** —— 没跑离线 A/B；
   实机 A/B 步骤见 §4.3 / §4.4。
3. **能否真的让 PX4 给出 200 Hz IMU** —— 需要改飞控 MAVLink 实例模式并重启，本轮没做。
4. **长时漂移**（分钟级以上）—— 未测。
5. **红外散斑（IR speckle）是否影响视觉** —— 之前把"IR 投影器是动态漂移根因"这个
   结论降级了：实测投影器只贡献约 5–10 个灰度级（0 mW → 93.84/92.02；
   360 mW → 98.90/100.97；关发射 → 93.08/91.23），而历史上 DYN50 与 LASEROFF3 的差距
   是 76 个灰度级，对不上。**关闭投影器仍然照做**（它只会让散斑变差），但别再声称它是根因。
6. **`init_max_disparity`** —— 同批次 A/B：0.3 → closure 0.0463 m，10.0 → 0.0277 m，
   现值 10.0 更优；但只有一次对照。
7. **`/tmp` 里那些外部脚本是谁拉起来的** —— 只确认了它们存在、内容和影响，没查到
   拉起者（父进程都是 init，说明是 detach 起的）。
8. **板上残留的 8 个历史 `.bak` 配置文件** —— 不影响运行（启动只读三个正式文件名），
   但没清理。
9. **`select window = 13`** —— 本轮日志里静态初始化器报 13 次
   `unable to select window of IMU readings`。这出现在**初始化成功之前**，属于初始化器
   每帧试跑的固有行为（IMU 缓冲还没攒满 1 s 窗口），初始化一旦成功就不再出现。
   判定为正常，但没有逐条核对。

---

## 7. 其它已经查清、容易被误传的点

- **重复性的边界**：同一批次内同配置重复跑，闭合误差差 ≤ 2%（0.0664 vs 0.0674）；
  但**换批次/重启后，同配置能差 163%**（0.0279 vs 0.0734，两个配置只有注释不同）。
  所以**只有同批次对照可以引用**，跨批次数字不能直接比。
- **OpenVINS 的 `dist` 不是可信的行程**（`VioManager.cpp:647-651`，只在存在 IMU clone
  时才累加）。
- **`[TIME]` 的语义**是单帧 CPU 耗时（`ROS2Visualizer.cpp:481`），它的 `hz` 是
  1/耗时，`behind` 在源码里乘了 100（×10 才是毫秒）。
- **投影器开关的真实语义**（实测）：`laser_power` 掉电保持；`emitter_enabled` 是
  流会话级的，每次开流都会被重置；**写入顺序有依赖**，必须先写 `laser_power` 再写
  `emitter_enabled`，否则后者会被拒绝。
- **外参量测约定已核对**：YAML 里存的是 `T_imu_cam`，OpenVINS 请求 `T_cam_imu`
  时会内部取逆（`ov_core/src/utils/opencv_yaml_parse.h` 的 `parse(...Matrix4d...)`）。
  用 `−R^T·t` 复算出的 `P_IinC` 与估计器启动打印的值**逐位吻合**，所以这个理解是可靠的，
  §1.4 的基线结论也因此成立。
- **`/odomimu_viz` 是限流后的可视化话题**，不要把控制或建图接到它上面。

---

## 8. Git 状态

- 远程 `origin/d430` HEAD：**`a55a449`**（本文档所在提交；上一状态是 `aaeb55b`）。
- 本次提交 `a55a449`（`fix(vio): correct the stereo baseline and make the prechecks
  self-healing`）包含：
  - `scripts/vio_precheck.py`：hw 阶段自愈 `laser_power`、IMU 速率策略改为
    100 Hz fail / 190 Hz 目标、新增双目基线强制校验、修引号比较 bug、新增
    dt p95 / 长间隔 / 非单调 / 微 dt 检查
  - `start_vio.sh`：启动时打印反推的双目实际基线
  - `scripts/set_extrinsics.sh`（新）：`rect50` / `baseline46` / `show`
  - `config/d430/kalibr_imucam_chain.yaml`：**改成 rect50**（仓库里的"生效配置"
    必须等于运行时生效配置，否则就是 §1.3 那个"运行时≠仓库"的根因本身）
  - `config/d430/kalibr_imucam_chain.rect50.yaml`（新，备用/可复现）
  - `config/d430/kalibr_imucam_chain.baseline46.yaml`（新，用于 A/B）
  - `docs/VIO_HANDOVER.md`（本文件）
- 板端运行时 SHA256（本轮实测生效值）：

```
6d678ed1c213d642f215d89d5c73bd2070267893a7346131cba9539b9e13a708  estimator_config.yaml
9c4c822244430d0d65979085063acde0e1dfc0d77c82e0a495598d36629a048d  kalibr_imu_chain.yaml
87afe8206b74f8010ee1ff954dc389c7ebb075da57e487b1eac8fb437620f01f  kalibr_imucam_chain.yaml   (= rect50)
6d90ff29467cbe11dd62b346c13dce88ddcf3edd39d1ff3805096cf6956e1302  vio_bridge_combined.py
d476e15370855c65c98193e9c26cd91dcd066ced4ac9e36d7113c237da06c4eb  imu_clock_mapper.py
```

板端 `gh_d430` 检出：**可能仍停在 `aaeb55b`**，拉一下即可：
`cd ~/kswlt/gh_d430 && git -c http.proxy= -c https.proxy= fetch origin d430 && git reset --hard origin/d430`
（运行时实际使用的那 5 个文件已单独部署，功能不受此影响。）
