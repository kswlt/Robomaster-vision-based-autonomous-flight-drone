# DEVELOPMENT PROGRESS — d430 VIO + Lightweight Navigation

> 开发日志（每次阶段性提交后追加）

---

## 2026-09-13 — Stage 0 完成：仓库与运行态审计

**完成内容**：完整审计 GitHub d430 分支代码与板子实际运行态（以代码+实测为准）。

**关键发现**：
1. 硬件确认：D430（PID 0x0AD1，FW 5.17.3.10，无 RGB 无 IMU），USB SuperSpeed 3.2 ✅
2. **相机流未运行**：`Error starting device: hwmon command 0x2c failed (-9)` = REC 硬件错误；infra1/2 Publisher count=0；VIO init=0 不初始化；odomimu 无发布
3. **launch 参数名错误**：`infra_fps/infra_width/infra_height` 不被 realsense2_camera 4.58.3 支持 → 已修复为 `depth_module.infra_profile:=848x480x30`（仓库+运行时同步）
4. **仓库代码过期**：vio_bridge_combined.py（10958B）缺 605/门控/重连；运行版在 ~/vio_ws（20557B）含全部功能 → 待同步
5. **仓库配置过期**：estimator_config.yaml（calib=true/chi2=0/disparity=0.5）与 kalibr_imucam_chain.yaml（单位阵外参）≠ 运行时稳定版（ENU 外参、chi2=1.0、disparity=0.2、标定关闭）→ 待同步
6. ESTIMATOR_STATUS flags：运行版 `&8`/`&2` 正确（POS_HORIZ_REL/VELOCITY_HORIZ）；仓库版注释错误 → 随 bridge 同步修复

**验证方式**：代码 diff + 实测 topic/hz/日志/USB 拓扑
**硬件验证状态**：未涉及飞行

**Commit**: 450c6d7
**Push**: origin/d430 success

**下一步**：Stage 1 恢复 D430 848×480@30

---

## 2026-09-13 — Stage 1 阻塞确认：D430 REC error（硬件级）

**完成内容**：
1. 修复 launch 参数（`depth_module.infra_profile:=848x480x30`），仓库 + 运行时同步
2. 新增诊断脚本 `scripts/check_camera_profile.sh`
3. 尝试恢复手段（均无效）：重启 vio.service ×2、USB authorized 重新枚举

**已确认**：`Error starting device: hwmon command 0x2c (9 1 0 0) failed (-9)`，REC 硬件级错误，软件无法绕过。

**Commit**: a0fa799
**Push**: origin/d430 success

---

## 2026-09-13 — Stage 1A 硬件层诊断完成（CASE A 确认）

**完成内容**：
1. 收集完整设备身份：D400 PID 0x0AD1（RS400_PID）、FW 5.17.3.10、USB SuperSpeed 5000M
2. **发现 librealsense 层身份异常**：module Serial = `ffffffffffff`（USB 层为 943623021659）、Recommended FW not supported
3. 最小 librealsense C++ 测试（绕过 ROS）：
   - Test A-E（infra1/infra2/stereo/depth，最保守 424x240@6）**全部失败**，同一 `hwmon 0x2c -9`
   - **profile 枚举完整正常**（IR1/IR2/Depth 848x480@30 均存在）
4. **0x2c 源码定位**：librealsense `fw_cmd::GET_ADV = 0x2C`；触发于 `RS2_OPTION_DEPTH_UNITS`(28) range 查询（option 探测仅此项失败）
5. 内核证据：`UVC control 11 on unit 3: -32 (EPIPE)` — XU 控制传输失败（hwmon 走 XU 通道）
6. 尝试固件 `hardware_reset()`（无破坏）：**无效**

**结论**：CASE A 成立 —— 问题在 RealSense 设备/固件/module/board 硬件层；已排除 ROS/参数/带宽/USB枚举/profile/固件运行状态。

**怀疑方向**：① module↔board 连接（interposer/排线）② module EEPROM 数据异常 ③ 供电 ④ firmware 组合 ⑤ module 硬件损坏

**Commit**: （本次提交）
**Push**: （本次提交）

**物理阻塞**：需要用户现场执行（按序）：彻底断电 30s 重插 → 换 USB 线 → 换 USB 口 → 检查供电（外接供电 hub）→ 检查 interposer/排线 → 记录 module/board 丝印。每步后跑 `bash ~/vio-improve/scripts/diagnose_realsense_hwmon.sh` 回报。
