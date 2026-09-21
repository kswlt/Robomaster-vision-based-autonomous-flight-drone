# AVOIDANCE_MODEL_AUDIT

**第一份审计报告 — 部署链路审计 / observation-action 对齐修复 / 离线 obstacle response benchmark**
**日期**: 2026-09-21 (JST)
**分支**: E2E-RL (HEAD `65290c2` 之前的状态；本报告对应的 commit 见文末)
**上游**: HenryHuYu/DiffPhysDrone @ `271936190b5c2a5e760230e718fa6b167718a5bf`（= 远端 master HEAD，已用 `git ls-remote` 确认）

---

## 0. 结论摘要（先读这里）

| 问题 | 结论 |
|------|------|
| A. 当前 checkpoint 本身是否有明显问题 | **不是根本不可用**：在训练一致的输入下，能正确刹车（正墙 1.5→1.0 m 间前向指令过零，0.35 m 处反向 5.6 m/s²）、左右规避方向正确、细柱强反应、门洞可通行、空旷无横向乱动。固有特性：**左右反应幅度不对称 ~1.6x**、**帧重复时输出漂移（单调增强刹车，方向安全）**、训练速度域（3–13 m/s）与目标 1.5 m/s 错位、训练相机下俯 20° vs 实机 D430 安装角未知 |
| B. 当前失败主要来自哪里 | **主要是部署链路（observation / coordinate / depth 多重失配）**，其次才是模型。决定性证据：legacy 符号翻转在 0.7 m 正墙处把"刹车"(-2.35) 反转为"冲墙"(+1.61)；margin=min(depth) 使 1.0 m 处刹车从 -2.73 削弱到 -0.57；INTER_AREA 在 3 m 细柱处稀释到 11.4 m；body_up 恒 [0,0,1]；safety brake 实际不存在。**这些修复前任何一项都足以让实机撞墙** |
| C. 是否有充分证据进入重训 | **当前无充分证据**（用户 gate 基于闭环指标）。静态响应测试只是前置门：修复后 6/8 判据 PASS。下一步必须先做 Level 2/3 闭环评测（observation 已对齐），用闭环数据决定。重训概率偏高（速度域错位 + D430 域 + 20° 俯角 + 左右不对称），但必须按用户 Stage 1–6 + 速度 curriculum 的流程走，**不能在重训前跳过闭环评测** |

---

## 1. 当前模型来源与恢复路径

```
HenryHuYu/DiffPhysDrone @ 2719361 (single-agent obstacle avoidance)
   └─ checkpoint0004.pth   (training/diffphys/upstream/checkpoint0004.pth, 514,496 params)
        └─ scripts/export_upstream_onnx.sh → deployment/common/export_onnx.py
             └─ deployment/onnx/upstream_avoidance.onnx  (39,775 B) + upstream_avoidance.onnx.data (2,057,984 B)
```

| 项 | 值 |
|----|----|
| ONNX SHA256（主体文件，前 16 位） | `05fd06520615b01f` |
| opset / IR / 节点数 | 18 / 10 / 27 |
| 输入 | `depth (1,1,12,16)`, `state (1,10)`, `gru_hidden (1,192)` |
| 输出 | `action (1,6)`, `values (1,1)`, `gru_hidden_out (1,192)` |
| git 跟踪状态 | **`upstream_avoidance.onnx` 未被 git 跟踪**（`.gitignore` 的 `*.onnx` 仅白名单 `policy.onnx`）；`.onnx.data` 已跟踪。本报告提交时修复：把部署模型加入跟踪，仓库可完整恢复 |
| Level 0 数值一致性 | PyTorch↔ONNX：28 组固定输入（7 深度 × 3 状态 + 5 步 GRU 链），**最大动作误差 2.38e-06**，余弦相似度 ≈1.0 —— 部署模型与训练 checkpoint 数值等价 |

---

## 2. 模型输入/输出（来自上游源码，非变量名推断）

### 2.1 state 10 维（`main_cuda.py` / `env_cuda.py`）

| 维度 | 语义 | 训练构造 | 部署修复 |
|------|------|----------|----------|
| 0–2 | local_v（当前速度，在帧 R 下） | `R.T @ velocity_world` | 同左（R = yaw-only 帧，见 2.3） |
| 3–5 | target_v（目标速度，在帧 R 下） | `R.T @ target_v`，`target_v` 按 `env.max_speed` clamp | 同左；**max_speed 用 1.5 m/s 固定（训练为每 episode 3–13 随机）** |
| 6–8 | **body_up（机体真实上向，世界系）** | `env.R[:,2]`（含 roll/pitch，推力方向） | **由 PX4 ATTITUDE roll/pitch/yaw（或四元数）构造完整 DCM 后取机体 z 轴（世界系）**；修复前恒 `[0,0,1]` ← **BUG** |
| 9 | margin（安全裕度标量） | `torch.rand(B)*0.2+0.1`，**每 episode 随机 [0.1,0.3] m，与障碍距离无关** | **固定 0.2 m（分布内），可从配置读取**；修复前 `min(depth)+clip[0.1,0.3]` ← **BUG** |

### 2.2 action 6 维（`main_cuda.py` 解码）

模型输出 6 维原始向量，上游用 `act.reshape(B,3,-1)` 解包（**交错布局** `[a_x, v_x, a_y, v_y, a_z, v_z]`）：
- col0 = `a_pred(3)`，col1 = `v_pred(3)`，均在帧 R 下；
- 真实净加速度指令 = `(R@a_pred − R@v_pred − g)·thr_est + g`，`g=[0,0,−9.80665]`，实机 thr≈1 ⇒ **`net = R@(a_pred − v_pred)`**；
- 修复前 web_vis 丢弃 `v_pred` 且对前两维做经验翻转 `*=-1` ← **BUG（见 §5.4 量化证据）**。

### 2.3 帧 R（yaw-only frame，`main_cuda.py` `self_forward_vec` 构造）

```
fwd  = normalize(body_forward 投影到水平面) = [cos(yaw), sin(yaw), 0]
left = cross(up, fwd) = [-sin(yaw), cos(yaw), 0]
up   = [0,0,1]
R    = stack([fwd, left, up], -1)   # 列向量
```
注意：**帧 R 不是完整机体帧**（忽略 roll/pitch），仅用于 local_v/target_v/action 的投影；**body_up 槽位必须用真实机体上向**。已证明：对 textbook 3-2-1 DCM，body-forward 的水平投影归一化恒等于 `[cos(yaw), sin(yaw), 0]`，因此仅用 PX4 yaw 构造帧 R 与训练一致（测试 `test_yaw_frame_matches_training_construction`）。

### 2.4 depth 输入（`env_cuda.py` + `quadsim_kernel.cu`）

```
训练: 渲染 64×48（tan-space, fov_x_half_tan=0.82, cam_angle=20° 下俯）
      → clamp(0.3, 24) → x = 3/d − 0.6 → max_pool2d(4,4) → (1,1,12,16)
恒等式: maxpool(3/d−0.6) ≡ 3/min(d)−0.6   （已验证 ✓，单调变换）
训练 depth 值 = 沿射线撞击参数 t ≈ 相机系 z-depth —— 与 RealSense z16 同语义
```

### 2.5 训练参数（configs/single_agent.args = 本地实测参数）

| 参数 | 值 | 与实机关系 |
|------|----|-----------|
| ctl_dt | 1/15 s ± jitter | 实机相机 30 Hz / 控制 20–33 ms —— **频率域错位** |
| pitch_ctl_delay / yaw_ctl_delay / act_lag | 12 / 6 / 1 步 | 训练含大控制延迟；实机链路延迟未测 |
| speed_mtp | 4 | 训练 max_speed 3–13 m/s；实机期望 ≤1.5 m/s —— **速度域错位** |
| cam_angle | 20° | 训练相机下俯 20°；D430 实机安装角未标定 |
| fov_x_half_tan | 0.82（HFOV≈78.7°） | D430 HFOV 87° —— 需 FOV 重映射（已实现面积最小重映射） |
| coef_collide / coef_obj_avoidance | 7.5 / 3.0 | — |

---

## 3. 坐标系（全部转换，均来自可证明的旋转矩阵）

| 系 | 定义 |
|----|------|
| NED | PX4 LOCAL_POSITION_NED / ATTITUDE 原生系：x=北, y=东, z=下 |
| NEU（world） | 部署用世界系：x=北, y=东, z=上（由 NED z 取反） |
| Body FRD（PX4 机体） | x=前, y=右, z=下；roll+ = 右滚, pitch+ = 抬头, yaw+ = 右转（MAVLink 约定） |
| Frame R | yaw-only 投影帧（列 = [fwd, left, up]，NEU） |
| RealSense optical | z=前, x=右, y=下（z16 深度即 z 轴距离） |
| 训练相机系 | z=前（depth=t≈z 距离），ray 方向 = R[:,0] − fu·R[:,2] − fv·R[:,1]；R_cam 绕 y 下俯 cam_angle |

**转换矩阵**（`deployment/common/upstream_obs.py`，已被 27 项单元测试锁定）：

```
C_nb (NED→body, textbook 3-2-1, 与 PX4 Dcmf 一致):
[[cT cY,  cT sY, -sT],
 [sR sT cY - cR sY, sR sT sY + cR cY, sR cT],
 [cR sT cY + sR sY, cR sT sY - sR cY, cR cT]]

四元数 DCM（MAVLink q = q_roll⊗q_pitch⊗q_yaw, Hamilton）与上矩阵逐元素一致（测试覆盖 10 组角度）
body-up(world NEU) = (−C[2,0], −C[2,1],  C[2,2])
body-forward(world NEU) = (C[0,0], C[0,1], −C[0,2])
NED→NEU: (x, y, −z)；NEU→NED: 同理
```

**修复前 web_vis 的做法（均无证明）**：`accel_body[0]*=-1; accel_body[1]*=-1` 经验翻转。修复后**全部符号来自上述矩阵**，禁止经验修补。

---

## 4. 已发现 Bug 清单（10 项，全部来自源码取证）

| # | Bug | 证据 | 状态 |
|---|-----|------|------|
| ① | `margin = min(depth)+clip[0.1,0.3]` 语义错位（应为训练随机 clearance 标量） | env_cuda.py `env.margin = torch.rand(B)*0.2+0.1`；web_vis.py `margin = np.clip(np.min(depth), 0.1, 0.3)` | 已修复（固定 0.2，可配置） |
| ② | body_up 恒 `[0,0,1]`（忽略 roll/pitch） | web_vis.py `up = [0,0,1]`；训练 `env.R[:,2]` 为真实推力方向 | 已修复（DCM 构造） |
| ③ | INTER_AREA 640×480→64×48 稀释亚像素障碍 | 3 m 细柱：conservative=3.0 vs legacy=11.4 m | 已修复（面积最小重映射） |
| ④ | 丢弃 `v_pred`，`net = R@a_pred` 而非 `R@(a−v)` | main_cuda.py 解码公式；web_vis.py 未用 vpred | 已修复（decode_action 完整实现） |
| ⑤ | `accel_body[0:2]*=-1` 经验翻转无坐标系证明 | 量化证据：0.7 m 正墙 legacy net=+1.61（冲墙）vs 修正 −2.35 | 已移除（保留 legacy 仅作 A/B） |
| ⑥ | safety brake 不存在（文档声称"closest<0.35m 切断前向"） | git 历史无 0.35 刹车代码；web_vis.py 仅有速度限制 | 未修复（**文档已更正**；实机前必须实现，属 Level 5 前置） |
| ⑦ | `upstream_avoidance.onnx` 未纳入 git | `.gitignore` `*.onnx` 仅白名单 policy.onnx | 已修复（加入白名单并提交） |
| ⑧ | target_env 碰撞项只在 rollout 末尾调用一次 `find_vec_to_nearest_pt()` | train_target_impact.py | **不改**（target-impact 与 avoidance 明确分开，见 §8） |
| ⑨ | Isaac 100% 成功率基于 synthetic_depth | eval_policy.py `--use_synthetic_depth` 默认 True（全 24m+中心 5×5） | 未修复（**Level 3 重建真实相机评测**，见 §10） |
| ⑩ | 训练速度域（3–13 m/s）与实机 1.5 m/s 错位 | speed_mtp=4；实机 MAX_SPEED=1.5 | 记录（重训时按速度 curriculum 处理） |

---

## 5. 修复内容

新共享模块 **`deployment/common/upstream_obs.py`**（训练一致单一事实来源，供 web_vis / inference / benchmark 共用）：

- 训练常量：GRAVITY、DEPTH_MIN/MAX、TRAIN_FOV、MARGIN 分布、D430 标称内参（运行时优先读 pyrealsense2 intrinsics）
- `yaw_only_frame` / `ned_to_body_dcm` / `dcm_from_quaternion` / `euler_to_quaternion` / `body_up_world_neu` / `body_up_world_from_quaternion`
- `remap_to_training_fov`：**面积最小重映射**（每个训练网格单元取落入该锥体的所有真实像素的最小值）——同时解决 FOV 对齐与细障碍保留（3/5 m 细柱实测保留）
- `preprocess_depth`：conservative（训练一致）与 legacy（仅 A/B）两模式 + valid_ratio / depth_min / p1 / p5 / median / p95 / near_ratio 统计
- `build_state` / `clamp_target_velocity` / `decode_action`（训练一致，交错布局解包）/ `legacy_decode_action`（仅对照）

单元测试 **`tests/test_coordinate_frames.py`**：27 项，覆盖机头朝北/朝东/朝南/朝西、roll±、pitch±、yaw±、DCM≡四元数、body-up 物理方向、速度/目标/加速度投影、state 槽位、NED↔NEU。全部通过。

### 5.1 修复前后对比证据

| 测试 | 修复前（legacy 链路） | 修复后（训练一致链路） |
|------|----------------------|------------------------|
| 0.7 m 正墙 | net_x = **+1.61（冲墙）** | net_x = **−2.35（刹车）** |
| 1.0 m 正墙 + margin=min | net_x = −0.57 | net_x = −2.73（margin 污染削弱刹车 ~4.8x） |
| 3.0 m 细柱 (11 px) | 深度稀释到 11.4 m（模型看不到） | 保留 3.0 m |
| 5.0 m 细柱 (6.7 px) | 最近邻重映射丢失（24 m） | 面积最小重映射保留 5.0 m |

---

## 6. Offline Obstacle Response Benchmark（`tools/test_policy_obstacle_response.py`）

**方法**：D430 pinhole 几何渲染 → 训练一致预处理（面积最小 FOV 重映射 + inverse + 4×4 maxpool）→ upstream_avoidance.onnx 推理（GRU 状态每场景重置，3 帧空场 warmup）→ 训练一致解码。state：local_v=0、target_v=1.5 m/s 前向、margin=0.2、body_up=level、yaw=0。**policy-only（不含 safety brake）**。

### 6.1 结果（`results/benchmark_all.json`，数值为 world NEU m/s²）

**A. 正墙距离扫描（net_x = 前向净指令）**

| 距离 | 3.0 | 2.0 | 1.5 | 1.0 | 0.7 | 0.5 | 0.35 m |
|------|-----|-----|-----|-----|-----|-----|--------|
| a_x（加速度） | +2.75 | +2.14 | +1.46 | −0.02 | −1.45 | −2.71 | −3.75 |
| net_x = a−v | +2.35 | +1.79 | +1.15 | **−0.51** | −2.35 | −4.08 | −5.63 |
| legacy net_x | −2.75 | −2.14 | −1.46 | +0.02 | +1.45 | +2.71 | +3.75 |

**判定 PASS**：前向指令在 1.5→1.0 m 间过零，0.35 m 处强烈反向（−5.63）。曲线见 `results/plots/frontal_wall_response.png`。注意 legacy 整条曲线被**反相**（远墙后退、近墙冲入）。

**B/C. 左右障碍（1.5 m 侧墙）**：左侧墙 → net_y = **−1.18（向右规避 ✓）**；右侧墙 → net_y = **+0.73（向左规避 ✓）**。PASS。

**D. 左右镜像对称**：`net_y(L)=−1.18` vs `net_y(R)=+0.73` ⇒ **幅度不对称 1.6x，FAIL**（方向正确、强度不同——模型固有特性，训练 random_rotation 未完全对称化）。

**E. 门洞（1.5 m，1.0 m 开口）**：net_x=+2.99, net_y=+0.28 ⇒ 穿洞通过，无振荡。PASS。

**F. 细柱（1.5 m，r=5 cm）**：ax 从空旷 +2.86 → **−0.11**，ay → −0.43 ⇒ 强反应（停止前冲并小幅绕行）。PASS。

**G. 空旷**：net=(+2.86, −0.10) ⇒ 保持前冲，无横向乱动。PASS。

**H. 帧重复（1.0 m 墙，重复 1/2/3/5 帧）**：net_x = −0.51 / −2.73 / −3.43 / −3.24 ⇒ **响应随重复帧单调增强，范围 2.9 m/s²，FAIL**（方向安全=增强刹车，但真实链路帧率抖动会改变输出幅度，实机需在闭环中确认稳定性）。

**I. 深度噪声**：5/10/20% 无效像素 → 输出与干净帧**完全一致**（保守 min 池天然抗洞）；高斯 σ=5 cm + 5% 洞 → net 从 (−0.51, +0.35) 变 (−4.52, +0.72)（噪声使块内 min 略近→刹车增强，方向正确）。PASS。

### 6.2 三个补充对照（§5.1 证据来源）

1. legacy 完整链路（INTER_AREA + margin=min + 翻转 + 无 vpred）@0.7 m 墙：**+1.61 冲墙** vs 修正链路 **−2.35**。
2. margin 污染：固定 0.2 vs margin=min(depth)，1.0 m 处 net_x −2.73 vs −0.57。
3. 预处理稀释：3 m 细柱 legacy=11.4 m / conservative=3.0 m；5 m 细柱最近邻重映射丢失、面积最小重映射保留。

---

## 7. A/B/C 三问结论（数据支撑）

**A. 当前 checkpoint 本身是否明显有问题？**
- 无明显"模型坏了"的证据：正墙刹车、左右方向、门洞、细柱、空旷全部方向正确（6/8 PASS）。
- 明确的模型固有特性：左右不对称 1.6x（FAIL）、帧重复响应漂移（FAIL）、训练速度域 3–13 m/s 与目标 1.5 m/s 错位、训练相机 20° 下俯与实机安装角未知。这些是"需在闭环中复核 / 重训时处理"项，不是"模型不可用"项。

**B. 失败主要来自哪一层？**
- **主因是部署链路，多因素共同作用**，按影响排序：
  1. **坐标/动作解码**：legacy 符号翻转使近墙时"刹车→冲墙"反转（+1.61 vs −2.35）——单独即可坠机；
  2. **margin 语义污染**：削弱近墙刹车 ~4.8x；
  3. **depth 预处理**：INTER_AREA 稀释亚像素障碍（3 m 柱 11.4 vs 3.0 m）；
  4. **body_up 恒 [0,0,1]**：倾斜飞行时 state 失真（实机待闭环量化）；
  5. **safety brake 不存在**：文档与代码不符，最后一道保护缺失。
- 模型贡献次要：左右不对称、帧漂移（方向安全）。

**C. 是否有证据进入重训？**
- **没有充分证据，第一阶段不重训**（符合用户 gate：观察对齐后闭环 collision_rate/safety_trigger 才是判据）。
- 修复后的静态证据**支持进入 Level 2/3 闭环评测**：observation 已对齐、模型方向正确。
- 预判：重训概率高（速度域错位 + D430 域 + 20° 俯角 + 左右不对称），但必须在闭环数据之后，按 Stage 1–6 + 0.5→0.8→1.0→1.2→1.5 m/s 速度 curriculum 执行。

---

## 8. target-impact 与 avoidance 明确分离

- `training/diffphys/target_env/train_target_impact.py` 的 wrong_collision loss **只在 rollout 末尾调用一次 `find_vec_to_nearest_pt()`**，中间时间步碰撞风险不进 trajectory loss，且未乘 v_to_obstacle（与上游不同）。`target_impact_eval_1000ep.json`（hit≈80.5% / wrong collision≈95.6%）是 **target-impact 任务**的指标，**不是避障指标**。
- **禁止**把 target-impact checkpoint 当避障模型部署；两者在 repo 与文档中明确分开。
- 重新训练避障应从官方 single-agent obstacle avoidance trainer 继承（用户 Stage 1），不从 target-impact trainer 出发。

---

## 9. 模型恢复性（Requirement 19）

- 已跟踪：`training/diffphys/upstream_commit.txt`（2719361）、`deployment/onnx/upstream_avoidance.onnx.data`。
- 本报告提交修复：**`upstream_avoidance.onnx` 加入 git 白名单并提交**，仓库可完整恢复部署模型。
- 记录：checkpoint `checkpoint0004.pth`（未入 git，可由上游 commit + 训练复现）、ONNX SHA256 `05fd06520615b01f…`、上游 commit `2719361`、导出脚本 `scripts/export_upstream_onnx.sh`。

---

## 10. Sim-to-Sim / Sim-to-Real 分级状态（Level 0–9）

| Level | 内容 | 状态 |
|-------|------|------|
| 0 | 网络 shape / ONNX 数值一致 | ✅ 28 组输入，最大误差 2.4e-06 |
| 1 | 人工 depth response | ✅ 本报告 §6（frontal/left/right/mirror/gate/pole/empty/framedrop/noise） |
| 2 | DiffPhys unseen random env | ⏳ 待跑（upstream 自带 eval 可跑，需确认 random seed 保存） |
| 3 | Isaac Sim rendered depth | ⏳ 待重建（**禁用 synthetic_depth**，真实 Camera/depth sensor 渲染 + 全场景随机化） |
| 4 | 真实 D430 offline replay | ⏳ 工具就绪（`tools/test_policy_obstacle_response.py --mode replay` + `--depth-path`），待录制 `datasets/real_depth_replay/` |
| 5–9 | 实机固定架 / 系留 0.3–0.5 / 0.8 / 1.0 / 1.5 m/s | ⛔ 未开始（前置：safety brake 实现、TTC 监控、速度/加速度限幅复核） |

**禁止跳级。** synthetic-depth 1000ep/100% 成功（CURRENT_STATE 历史记录）**不得**作为模型避障性能证据。

---

## 11. 遗留事项 / 下一阶段（不跳级）

1. **实机前必做**：实现并测试真正的 safety brake（closest<0.35 m 或 TTC 阈值切断前向）+ OFFBOARD watchdog + 速度/加速度限幅 + 高度保护；把 web_vis.py 的 `UpstreamAvoidancePolicy` 切换到 `upstream_obs.py`（含完整姿态、固定 margin、保守预处理、训练一致解码）。
2. **闭环评测**：Level 2（DiffPhys eval）→ Level 3（Isaac rendered depth，全场景随机化 + 种子保存），输出用户 §6 全部指标（collision_rate / clearance / TTC / 触发率 / 延迟等），**policy-only 与 policy+safety 分开统计**。
3. **实机 D430 录制**：`deployment/rk3588/record_debug.py` 类工具录真实 depth（timestamp/raw/processed/姿态），供 Level 4 replay。
4. **重训决策门**：闭环数据上按用户 gate（collision_rate>2% 或 safety_trigger>5% 或基础场景频繁失败 → 重训）。
5. 若重训：Stage 1–6（官方 trainer → 实机动力学 → D430 DR → delay → RM 障碍 → RM STL），速度 curriculum 0.5→1.5 m/s。

---

## 12. 复现

```
python -m pytest tests/test_coordinate_frames.py            # 27 passed
python tools/validate_onnx_vs_torch.py                      # 28 cases, max err 2.4e-06
python tools/test_policy_obstacle_response.py --mode all    # 写 results/benchmark_all.json + plot
```

**本报告对应 commit**：见 `git log`（fix(policy) / test(policy) / docs(audit) 三个小步提交，本报告为 docs(audit) 提交）。
