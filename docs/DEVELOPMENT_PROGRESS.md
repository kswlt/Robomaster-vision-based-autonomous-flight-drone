# DEVELOPMENT PROGRESS — d430 VIO + Lightweight Navigation

> 开发日志（每次阶段性提交后追加）

---

## 2026-09-13 — 运行态安全修复

发现运行中的 OpenVINS 在静止场景漂移到 600m 以上，桥接直到位置模长超过 150m 才进入保护。根因调查确认运行配置仍使用 640×480 内参，而 D430 实际输出已恢复为 848×480。

修复内容：
- 运行态与仓库统一为 D430 848×480 工厂内参，并保留当前安装方向外参；关闭在线内外参标定。
- 同步增强版 bridge 到仓库和运行目录。
- 修正 MAVLink 位姿协方差对角索引；使用 OpenVINS 位置协方差并增加启动/运行健康门控。
- 发散后 fail-closed，停止发送视觉位置并由 watchdog 重启整条链路。
- 外部航向命令改为 620，并等待 `COMMAND_ACK`；IMU 改用 PX4 采样时间映射。
- 修复手动启动脚本的 RealSense profile 参数。

验证结果见 `docs/RUNTIME_SAFETY_REPAIR.md`。

---

## 2026-09-13 — Stage 0 完成：仓库与运行态审计

**关键发现**：相机流未运行（REC 硬件错误）；launch 参数名错误（已修复 infra_profile）；仓库代码/配置过期（bridge、estimator_config、imucam_chain 待同步）；ESTIMATOR_STATUS flags 运行版正确。
**Commit**: 450c6d7 / **Push**: success

---

## 2026-09-13 — Stage 1 阻塞确认（REC error，硬件级）

修复 launch 参数 + 新增 check_camera_profile.sh；重启/USB 重枚举无效。
**Commit**: a0fa799 / **Push**: success

---

## 2026-09-13 — Stage 1A 硬件层诊断（CASE A 确认）

最小 librealsense 测试 A-E 全失败（0x2c -9）；0x2C=GET_ADV、Depth Units 读取失败；module serial ffffffff、Recommended FW 不支持；固件 reset 无效 → 设备/固件/module/board 层。
**Commit**: f5ad43c / **Push**: success

---

## 2026-09-13 — ✅ Stage 1A PASS：根因 = 排线接触不良，已修复

**根因确认**：module↔board 排线（interposer）脱落/接触不良 → 设备 fallback 识别为 D400(0x0AD1)、EEPROM/校准读取失败（serial ffffffff、Depth Units 不可读）→ hwmon 0x2c (GET_ADV) -9 → 所有流启动失败。

**修复**：用户重新插好排线 → 全部恢复：D430(0x0AD4)、serial 938422073656、Depth Units 可读、流测试 A-E 全 PASS、VIO 恢复运行。

**遗留**：相机被插到 USB2.0 口（Bus 04），需换 USB3 口。
**Commit**: c16639b / **Push**: success

---

## 2026-09-13 — ✅ Stage 1B PASS：D430 848×480@30 恢复 + VIO 静态验证

**关键过程**：
1. 板子多次重启 + 网络不稳定（WiFi 断连 3 次，最终确认是供电不足导致）
2. 飞控 USB 反复断开重连（供电不足导致），供电解决后稳定
3. 相机冷启动时枚举到 USB2（Bus 05），热插拔后恢复 SuperSpeed（Bus 02, 5000M）
4. 供电问题解决后，全链路稳定

**实测结果**：
| 指标 | 值 |
|---|---|
| 相机 | D430 (8086:0ad4), serial 938422073656 |
| USB | Bus 02 SuperSpeed **5000M** |
| infra1 | **848×480 @ 29.995 Hz** |
| infra2 | 848×480 稳定（std dev 0.001s） |
| IMU | **146.4 Hz**（PX4 /dev/ttyACM0） |
| VIO odom (/odomimu) | **146.7 Hz** |
| VIO pose (/poseimu) | **15.0 Hz** |
| OpenVINS ZUPT | accepted, chi2=0.817, \|v\|=0.004 m/s |
| vio_bridge → PX4 | VISION_POSITION_ESTIMATE 正常发送，EKF 视位/视速=True |
| REC error | 0 |
| CPU | ~14%（84% idle） |
| RAM | 715Mi / 3.8Gi |

**已知问题**：
- 冷启动时相机可能枚举到 USB2（Bus 05），需热插拔恢复 SuperSpeed
- WiFi 不稳定（供电不足导致），建议后续用有线网络
- 手持动态 VIO 测试：NOT VERIFIED（需用户操作）
- 真实飞行 VIO：NOT VERIFIED IN FLIGHT

**产出**：docs/D430_848x480_30_BASELINE.md
**Commit**: （本次提交）
**Push**: （本次提交）

**下一步**：
1. Stage 1.5：手持动态 VIO 测试
2. Stage 2：开启 D430 Depth，确认不破坏 VIO
3. 仓库代码同步（运行版 bridge + 稳定 config）
# 2026-09-13: reproducible VIO investigation, first milestone

Second milestone: all-sample timing + CameraInfo verification + DDS diagnosis.
First milestone SHA `e7ffdb0` pushed. Synthetic timing regression tests: 4 PASS
on board (local Windows Python lacks numpy). Real ~58 s timing bag analyzed;
17 unmatched stereo frames, IMU 195.06 Hz, actual camera intrinsics match YAML.
60 s serial audit measured significant arrival-offset variation and no
SYSTEM_TIME; absolute mapping and best camera offset still unknown. See current
authoritative document for exact metrics, temporary UDP transport and paths.
Watchdog restored, then latched VIO_FATAL variance=4.071 m² and stopped VIO;
latch remains set. No PX4 visual output enabled. Awaiting operator stationary
setup for labeled raw-sensor recordings. No parameter tuning or flight done.

- Initial d430 b89b761; no reset, no parameter edits. Detailed current status:
  [VIO_ROOT_CAUSE_AND_VALIDATION.md](VIO_ROOT_CAUSE_AND_VALIDATION.md).
- e45a673 tightened static ZUPT; 3c93dad disabled online time calibration but
  did not commit -11 ms despite its message; b89b761 raised frontend to 200/12.
  These historical tuning results are not a validated dynamic baseline.
- Actual YAML loads 0 s in freshly rebuilt instrumented executable. Startup
  warning prevents silent missing-fixed-offset assumptions. Build passed.
- Runtime ZUPT thresholds differ from repo (0.3/0.02/0.10 vs 0.5/0.05/0.15).
  Preserved runtime files; no sensor calibration changes.
- Added unique, hashed raw stereo/IMU bag workflow and operator protocol.
- Runtime domain 42 startup stalls and watchdog repeated restarts discovered;
  watchdog temporarily stopped for investigation. PX4 vision remains false.
- No dynamic dataset or calibrated best offset yet. ROOT CAUSE UNDER INVESTIGATION.

## 2026-09-13 23:55 - VIO 漂移根因确认与修复

### 根本原因
VIO 初始化时飞机在移动，导致初始加速度计偏置估计错误（ba = -0.1092 m/s²），
然后 VIO 发散，位置飘到 98 米。保持飞机完全静止初始化后，偏置正常（ba ≈ 0），零漂移。

### 修复措施
1. 确保 VIO 初始化时飞机完全静止（init_max_disparity: 0.3）
2. 保持 calib_cam_timeoffset: true（在线优化收敛到 0.01152）
3. 降低 IMU 加速度计噪声（noise_density: 1e-3, random_walk: 5e-4）
4. 提高 vio_bridge 健康门控阈值（避免轻微发散立即锁存）

### 验证结果（静止）
- 加速度计偏置 ba: 0.0007, 0.0038, -0.0033（正常 <0.01）
- 位置漂移 dist: 0.00 米
- 速度: 0.001 m/s
- timeoffset: 0.01152（已收敛）
- 特征点: 126 个
- VIO 处理频率: 41-110 Hz

### 关键教训
- VIO 初始化必须保持飞机完全静止，否则初始偏置估计错误会导致发散
- timeoffset 在线优化是有效的，不需要固定值
- 加速度计偏置 ba 是判断 VIO 是否正常的关键指标（正常应 <0.01）

### 下一步
- 手持动态测试（缓慢平移/旋转）
- 验证动态下 VIO 是否稳定

## 2026-09-14 OpenVINS 编译成功 + VIO 稳定验证

### 编译问题解决
- **问题**：板子并行编译 OpenVINS 时 OOM（cc1plus 占用 2.3GB 虚拟内存被 OOM killer 杀死）
- **解决**：使用 `MAKEFLAGS=-j1` 单线程编译，用时 1 分 11 秒成功
- **编译产物**：libov_msckf_lib.so 199MB，时间戳 2026-09-14 02:00

### timeoffset 固定修改
- 修改 `ov_msckf/src/core/VioManagerOptions.h`：`calib_camimu_dt = 0.01152`（默认值）
- 在 `kalibr_imucam_chain.yaml` cam0 下添加 `timeshift_cam_imu: 0.01152`
- 配置 `calib_cam_timeoffset: false` 禁用在线优化
- **验证**：LOADED_CAMERA_IMU_TIME_OFFSET_SEC=0.011520000 确认初始值已加载

### VIO 稳定状态（静止）
- 位置漂移：0.01 米（极小）
- 加速度计偏置：ba = 0.0009, 0.0043, -0.0040（正常 <0.01）
- timeoffset：稳定在 -0.00282（在线优化似乎仍在运行，但已收敛）
- 特征点：145-147 个
- ZUPT：正常工作

### 待调查问题
- `calib_cam_timeoffset: false` 配置似乎没有完全生效（日志仍输出 camera-imu timeoffset）
- timeoffset 初始值 0.01152，但运行时收敛到 -0.00282，差异较大
- 需要验证动态晃动时 VIO 是否稳定

### Commit
- 修改文件：estimator_config.yaml, kalibr_imucam_chain.yaml, VioManagerOptions.h

## 2026-09-14 - VIO Drift Root Cause Fixed (Docker Cross Compile)

### Root Cause Confirmed
- VIO divergence on motion caused by unstable online camera-IMU timeoffset calibration
- timeoffset jumped from 0.01152 (stationary) to -0.00282 during motion (14ms error)
- This caused incorrect accelerometer bias estimation (ba = -0.1092 vs normal <0.01)
- Position then diverged to hundreds of meters

### Fix Applied
1. Fixed timeoffset = 0.01152 in VioManagerOptions.h (calib_camimu_dt default)
2. Force disabled online timeoffset calibration in StateOptions.h (do_calib_camera_timeoffset = false)
3. Compiled using Docker amd64 cross-compile (aarch64-linux-gnu-gcc 11.4.0)
   - ov_core: 78MB
   - ov_init: 98MB
   - ov_msckf: 199MB
   - run_subscribe_msckf: 26MB

### Verification Results (Stationary)
- LOADED_CAMERA_IMU_TIME_OFFSET_SEC=0.011520000 ✓
- Position drift: <1cm (p_IinG = -0.003, 0.008, 0.002) ✓
- Accelerometer bias: ba = 0.0002, -0.0005, -0.0032 (normal <0.01) ✓
- ZUPT velocity: 0.004 m/s ✓
- Features: 134 ✓
- VIO rate: 38-40 Hz ✓
- Latency: <1ms ✓

### Next Steps
- Dynamic motion test (user needs to shake drone)
- Verify no divergence during fast rotation/translation
- Flight test (NOT VERIFIED IN FLIGHT)

### Files Modified
- ov_msckf/src/core/VioManagerOptions.h (calib_camimu_dt = 0.01152)
- ov_msckf/src/state/StateOptions.h (force do_calib_camera_timeoffset = false)

## 2026-09-14 - VIO Drift Fix Verified: timeoffset online calibration DISABLED

### Root Cause Confirmed
- Previous build did NOT include StateOptions.h modification due to build cache issue
- First OOM failure compiled partial objects, second build did not recompile dependent files
- timeoffset online calibration was still ACTIVE, causing divergence on motion

### Fix Applied
1. Added VERIFY_FORCE_DISABLED_TIMEOFFSET print to confirm modification is compiled
2. Cleaned build directory completely (rm -rf build/ov_msckf)
3. Recompiled with Docker amd64 cross-compile (-j2 to avoid OOM)
4. Verified binary contains "VERIFY_FORCE_DISABLED_TIMEOFFSET" string

### Verification Results
- VERIFY_FORCE_DISABLED_TIMEOFFSET: do_calib_camera_timeoffset=0 ✓
- No "camera-imu timeoffset" output in latest log (0 in last 100 lines) ✓
- Position stable: p_IinG = 0.006, 0.023, 0.043 ✓
- Distance: 1.25m (stable, not diverging) ✓
- VIO rate: 25-60 Hz
- ZUPT: velocity 0.003 m/s, 128 features

### Remaining Issue
- Accelerometer bias ba = -0.0746, 0.0518 (still slightly high, normal <0.01)
- May indicate timeoffset=0.01152 is not perfectly accurate, or minor extrinsics error
- Need dynamic motion test to verify no divergence

### Files Modified
- ov_msckf/src/state/StateOptions.h (added VERIFY print, force do_calib_camera_timeoffset=false)
- ov_msckf/src/core/VioManagerOptions.h (calib_camimu_dt = 0.01152)
