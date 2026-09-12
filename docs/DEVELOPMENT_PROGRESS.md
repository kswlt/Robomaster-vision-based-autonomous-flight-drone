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

## 2026-09-13 — Stage 1 阻塞：D430 REC error 确认（物理硬件故障）

**完成内容**：
1. 修复 launch 参数（`depth_module.infra_profile:=848x480x30`），仓库 + 运行时同步
2. 新增诊断脚本 `scripts/check_camera_profile.sh`
3. 尝试恢复手段（均无效）：
   - 重启 vio.service（2 次）→ 同样 hwmon 错误
   - USB authorized 重新枚举（2-1, SuperSpeed 正常）→ 同样 hwmon 错误

**已确认**：
- 相机设备枚举正常（D400, 0x0AD1, FW 5.17.3.10, USB 3.2 SuperSpeed）
- 启动流失败：`Error starting device: hwmon command 0x2c (9 1 0 0) failed (response -9= No expected user action)`
- 这是 **REC 硬件级错误**，软件（参数/重启/重新枚举）无法绕过
- 与交接文档 7.13 结论一致：需物理处理（换 USB 线/换 USB 口/改善供电）

**硬件验证状态**：相机流未恢复，VIO 不可运行

**Commit**: （本次提交）
**Push**: （本次提交）

**物理阻塞点（需要用户现场执行）**：
1. 换 USB 线（高质量、尽量短、USB3 认证线缆）
2. 换 USB 口（板子其他 USB3 口，避开当前 2-1）
3. 改善供电（外接带电源 USB hub）
4. 完成后在板端执行 `bash ~/vio-improve/scripts/check_camera_profile.sh` 复查
5. 预期：camera.log 出现 `Open profile` 且 Width=848 Height=480 FPS=30；infra1/2 Publisher count=1；topic hz ≈30Hz

**下一步**：恢复 848@30 → 生成 D430_848x480_30_BASELINE.md → Stage 1.5 VIO baseline
