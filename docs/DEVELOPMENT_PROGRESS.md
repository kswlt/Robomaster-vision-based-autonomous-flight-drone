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
