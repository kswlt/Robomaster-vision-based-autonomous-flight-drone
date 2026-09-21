# Current State

**Last updated**: 2026-09-21 (JST) — web_vis 已接入训练一致链路
**Branch**: E2E-RL (HEAD: 65290c2 + stage-1 commits)

## 2026-09-21 Avoidance Stage 1 — Deployment Audit & Offline Benchmark

**主线任务已切换为"端到端强化学习无人机避障"（PX4 OFFBOARD + D430 前视深度 + upstream avoidance 模型）。以下内容替代此前以 target-impact（撞击）为目标的全部状态表述。详见 docs/AVOIDANCE_MODEL_AUDIT.md。**

| 项 | 状态 | 说明 |
|----|------|------|
| 上游 DiffPhys 审计 | ✅ | commit 2719361 已核对；observation/action/坐标系/预处理逐维取证 |
| observation 对齐修复 | ✅ | 新 `deployment/common/upstream_obs.py`：margin 固定 0.2、完整 DCM body_up、训练一致解码（a−v）、面积最小 FOV 重映射、无效深度统计 |
| web_vis 接入 | ✅ | deployment/rk3588/web_vis.py 已切换到 upstream_obs 唯一实现（删除 INTER_AREA / margin=min / body_up 恒值 / accel·vpred sign flip / net_accel=accel_world）；body_up 用 PX4 完整 roll/pitch/yaw，margin 固定 0.2；benchmark 直接实例化 web_vis 策略类，实机与离线链路逐字节一致 |
| 坐标系单元测试 | ✅ | tests/test_coordinate_frames.py，27 passed |
| Level 0 ONNX 数值 | ✅ | PyTorch↔ONNX 28 组输入最大误差 2.4e-06 |
| Level 1 离线响应 benchmark | ✅ | results/benchmark_all.json（**web_vis 链路**）：正墙 3.0→1.5 m 减速、1.0 m net_x=−0.45、0.7 m −2.27、0.35 m −5.60；左右方向正确 PASS；门洞/细柱/空旷 PASS；镜像幅度不对称 1.6x FAIL、帧重复漂移 FAIL |
| 重训决策 | ⏳ | 静态证据不足以判定；先跑 Level 2/3 闭环，按 gate（collision_rate>2% / safety_trigger>5%）决定 |
| Isaac 真实相机评测 | ⏳ | **禁用 synthetic_depth**（历史 100% 成功率即 synthetic 输入，不算避障证据） |
| 实机 safety brake | ❌ | **代码中不存在**（历史文档声称存在，git 已查证为假）——实机前必须实现 |
| upstream_avoidance.onnx 入 git | ✅ | 本阶段修复 `.gitignore` 白名单并提交（SHA256 05fd06520615b01f…） |

**重要更正（历史文档已过时/矛盾，以此为准）**：
1. "1000ep 100% hit / 80.5% hit" 均为 **target-impact（撞击）任务**指标，**不是避障能力证据**；target-impact 与 avoidance 在 repo/文档中明确分离。
2. "safety brake（closest<0.35m）" 在代码中不存在，文档声明与实际不符，已更正。
3. "D430 硬件故障确认（2026-09-17）" 为当时诊断记录；当前任务前提为 D430 可用。若故障复现需重启该诊断流程。
4. Isaac "100% success" 基于 synthetic depth（全 24m+中央 5×5），已弃用作避障依据，Level 3 重建真实渲染评测。

**下一阶段（不跳级）**：Level 2 DiffPhys unseen eval → Level 3 Isaac rendered-depth 闭环（全随机化+种子保存）→ 重训决策 gate → Level 4 真实 D430 replay。

---
# Current State

**Last updated**: 2026-09-17 (JST)
**Branch**: E2E-RL (orphan rebuild)

## 2026-09-17 Camera Diagnosis (P0 Blocker)

**D430 硬件故障确认**（在完全停止 VIO 系统后复查）：
- UVC control 1 on unit 3 持续返回 -32 (EPIPE)，与用户空间无关
- 深度流(video0 Z16)和红外流(video2 GREY)全部失败（select timeout / XU busy）
- uvcvideo 是内核内置模块，无法卸载复位；USB authorized 断电在 RK3588 ehci-platform 上无效
- pyrealsense2 能枚举设备但 XU 控制失败，hardware_reset 无法执行
- **次要发现**：橙Pi5上运行独立 VIO 系统（vio.service + watchdog_camera.service），以 `enable_depth:=false` 占用相机。完全停止后相机仍不工作，确认硬件故障为主因。
- **修复路径**：① 换 USB 3.0 口（当前在 USB 2.0，496mA 接近上限）② 更换 24-pin FPC 排线 ③ 更换 D430 相机
- VIO 当前已停止（排查时停掉），如需恢复：`sudo systemctl start vio.service watchdog_camera.service`

## Completion

| Area | Status | Details |
|------|--------|---------|
| Git rebuild | ✅ Done | Orphan E2E-RL, remote fetched, proxy configured |
| Input asset backup | ✅ Done | C:\RM_E2E_INPUT_BACKUP\, SHA256 recorded |
| Environment audit | ✅ Done | docs/ENVIRONMENT.md |
| STL analysis | ✅ Done | Unit=meters, 28×15m, 124995 tris, artifact at z=18 |
| Armor image analysis | ✅ Done | Bracket 135×38mm, rigidity 60N/2.5°, plate dims TODO |
| Project skeleton | ✅ Done | configs/, docs/, sim/, training/, deployment/, scripts/, tests/ |
| Configs | ✅ Done | 7 YAML files with real data |
| Isaac Sim install | ✅ Done | 6.1.0 standalone at C:\isaacsim, post_install complete |
| Isaac Sim scene code | ✅ Done | sim/isaac/*.py — updated for Isaac 6.1.0 API, executed in real Isaac |
| Scripted baseline | ✅ Done | controller.py + episode.py — **real Isaac 20ep 100% hit** |
| Headless eval | ✅ Done | evaluate.py + run_eval.ps1 — **real Isaac 20ep 100% hit**, JSON+CSV output |
| DiffPhys env build | ✅ Done | WSL2: PyTorch 2.2.2+cu118, CUDA 11.8, quadsim_cuda built & verified |
| DiffPhys upstream training | ✅ Done | 3000 iters: loss 27.3→3.3; checkpoint save/load verified (514K params) |
| Target-impact training | ✅ Done | 6000 iters, 1000ep eval: **80.5% hit rate**, impact_vel 0.8m/s, angle 41.9° |
| Isaac real physics eval | ✅ Done | **Milestone 1: 20/20 hit, 100% rate, 0 wrong, 0 timeout** |
| Checkpoint→Isaac eval | ✅ Done | **Milestone 4: 1000ep 100% hit, impact angle 23.6°, vel 0.84m/s** |
| RK3588 ONNX export | ✅ Done | **35.9KB ONNX, validated, ORT diff 9.5e-07** |
| Sim-to-Real noise test | ✅ Done | **100% hit across none/light/moderate/heavy**, angle 23.6°→58.1° |
| RK3588 ONNX export | ✅ Done | **35.9KB ONNX, validated, ORT diff 9.5e-07** |
| RKNN conversion | ⏳ Pending | ONNX ready, needs RKNN Toolkit2 + RK3588 hardware |

## Verified

- STL loads in trimesh, geometry analyzed, unit calibrated to meters
- Arena reference images confirm 28m×15m official battlefield
- Armor bracket dimensions extracted from engineering drawing
- WSL2 GPU access confirmed (nvidia-smi works inside Ubuntu)
- GitHub remote accessible via Clash proxy (repo-local config)
- Python 3.14 + numpy 2.5.2 + trimesh 5.1.0 + matplotlib 3.11.2 on Windows
- **quadsim_cuda extension built and importable**: all 6 functions verified
- **DiffPhys training starts and loss decreases**: 27.3→3.3 in 3000 iters
- **Checkpoint save/load verified**: checkpoint0003.pth (3000 iters), 514,496 params, CPU+GPU forward pass OK
- **Target-impact training complete**: 6000 iters, 1000ep eval: **80.5% hit rate**, impact_vel 0.8m/s, angle 41.9°
- **Isaac Sim 6.1.0 installed**: standalone ZIP at C:\isaacsim, post_install done
- **Isaac Sim 6.1.0 Python env verified**: isaacsim.SimulationApp, isaacsim.core.api.world.World, isaacsim.core.api.objects, warp 1.16.0 CUDA
- **Kinematic fallback eval**: 20 episodes, 100% hit rate, full metrics pipeline
- **Milestone 1 — Real Isaac scripted baseline**: 20/20 episodes hit=True, 100% target_hit_rate, 0 wrong_collisions, 0 timeouts, impact_velocity_mean=1.18 m/s

## Current Blockers

1. **Armor module exact dimensions** — placeholder 0.135×0.055m. Need official RMUC 2026 spec.
2. **Armor plate normal/orientation** — defaulted to face -x; needs STL face normal analysis.
3. **Impact velocity low (0.8 m/s in DiffPhys, 1.18 in Isaac)** — policy approaches slowly. More training or higher speed_mtp may improve.
4. **Impact angle 155° in Isaac** — angle calculation may have sign/frame bug. Need to verify.
5. **Checkpoint→Isaac not yet validated** — policy_wrapper.py written but not run with real checkpoint.

## Next Steps

1. ~~Test Isaac Sim Python environment~~ ✅ Done
2. ~~Run scripted baseline in real Isaac Headless (milestone 1)~~ ✅ Done
3. Import target-impact checkpoint into Isaac, run 1000 episodes (milestone 4)
4. Fix impact angle calculation bug
5. Add depth noise/domain randomization, re-evaluate (milestone 5)
6. Export ONNX/RKNN for RK3588 (milestone 5)
