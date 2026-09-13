# DEVELOPMENT PROGRESS — d430 VIO + Lightweight Navigation

> 开发日志（每次阶段性提交后追加）

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

**修复**：用户重新插好排线 → 全部恢复：
- 正确识别 **D430（PID 0x0AD4）**，serial 938422073656
- Depth Units 恢复可读（def=0.001）、Laser Power 支持（D430 有激光）
- **最小 librealsense 流测试 A-E 全部 PASS**（infra1/infra2/depth/全开）
- **VIO 恢复运行**：OpenVINS ZUPT 正常、97 features、chi2 达标
- hwmon 0x2c 错误消失、无持续 REC error

**硬件验证状态**：Stage 1A Gate 全过（枚举✅ 身份✅ 流启动✅ 0x2c消失✅ 收帧✅ USB SuperSpeed 曾确认✅）

**遗留 ⚠️**：相机被插到 **USB2.0 口（Bus 04, 480M）** → profile 表被裁剪（848x480 仅@10/8/6）、realsense2_camera 报 `848x480x30 invalid` 回退 640x480@15。需换插 USB3 口（Bus 02, 5000M）后重启 vio.service 进入 Stage 1B。

**Commit**: （本次提交）
**Push**: （本次提交）

**下一步**：① 用户换插 USB3 口 ② 重启 vio.service 验证 848x480@30 ③ D430_848x480_30_BASELINE.md ④ Stage 1.5 VIO baseline
