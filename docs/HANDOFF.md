# E2E-RL 项目交接文档

> 新 Agent 读完本文档即可接手。所有路径、命令、硬件信息均为最新验证状态。

---

## 1. 项目目标

RoboMaster 小型无人机**视觉端到端目标撞击**：
- 输入：深度图 + 目标相对位置 + 机体速度 + 姿态/重力方向 + GRU 隐状态
- 网络：CNN(3层Conv) + GRUCell(192) + Linear → 高层控制量（加速度/速度）
- 任务：HOME → 起飞 → 高速飞向固定装甲板 → 主动撞击 → 恢复 → 返回 HOME
- 撞中装甲板 = SUCCESS，撞其他结构 = FAILURE
- **最终平台：RK3588（橙Pi5），不是 Jetson Orin NX**
- 训练：Windows PC + NVIDIA GPU（WSL2/CUDA + DiffPhysDrone）
- 验证：Windows Isaac Sim 6.1.0（独立 validator，不参与训练）

---

## 2. 仓库与 Git

| 项 | 值 |
|----|-----|
| 本地路径 | `C:\Users\Admin\Desktop\端到端强化学习无人机仿真\` |
| GitHub | https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone |
| 工作分支 | `E2E-RL`（orphan 重建，已彻底覆盖旧代码） |
| 最新 commit | `aa3d21f`（已 push） |
| 保护分支 | `main`、`master`、`d430` — **禁止 force push** |
| Git 代理 | repo-local `http.proxy=http://127.0.0.1:7890`（Clash 需运行在 7890） |
| 输入资产备份 | `C:\RM_E2E_INPUT_BACKUP\`（STL + 装甲板图片，含 SHA256） |

**Git 规则**：每阶段完成立即 commit + push；首次重建用了 `--force-with-lease`，后续正常 push；`upstream/` 和 `venv/` 在 `.gitignore` 中。

---

## 3. 已完成里程碑（全部验证通过）

| 里程碑 | 状态 | 关键结果 |
|--------|------|----------|
| M1: Isaac scripted baseline 20ep | ✅ | 20/20 hit, 100%, 0 wrong collision |
| M2: DiffPhys upstream 复现 | ✅ | 10000 iters, loss 27.3→3.3, checkpoint 可重载 |
| M3: Target-impact 训练 1000ep | ✅ | 6000 iters, 80.5% hit（DiffPhys 环境） |
| M4: Checkpoint → Isaac 1000ep | ✅ | **1000/1000 hit (100%)**, impact angle 23.6°, vel 0.84m/s |
| M5: 噪声测试 + ONNX 导出 | ✅ | 4级噪声全部 100% hit; ONNX 35.9KB, ORT 推理误差 9.5e-07 |
| M6: 橙Pi5真机部署 | ✅ | 项目 clone + 依赖安装 + main.py 运行 |
| M7: 真实深度算法验证 | ✅ | D430 640×480@30, Policy 2.87ms, 4项 sanity check 全过 |

---

## 4. 真机硬件（橙Pi5）

### 4.1 SSH 连接

```
IP:   100.119.45.114 (Tailscale)
用户: orangepi
密码: orangepi
主机名: orangepi5
```

**连接方式**：Windows 端用 `scripts/opi5_ssh.py`（paramiko 封装，密码认证）。
普通 ssh 公钥认证失败，必须用密码。

```powershell
# 执行单条命令
python scripts/opi5_ssh.py "命令"

# Python 中使用
from scripts.opi5_ssh import connect, sftp_put
client = connect()
stdin, stdout, stderr = client.exec_command("命令")
sftp_put(local_path, remote_path)  # 上传文件
```

### 4.2 硬件清单

| 设备 | 型号 | 接口 | 状态 |
|------|------|------|------|
| 计算板 | Orange Pi 5 (RK3588, 4GB RAM) | - | ✅ 运行中 |
| 深度相机 | Intel RealSense D430 | USB（当前 Bus 004, USB 2.0） | ✅ 640×480@30 |
| 飞控 | MicoAir743AIO (ArduPilot) | /dev/ttyACM0 @ 921600 | ✅ 已连接 |
| 系统 | Ubuntu 22.04 aarch64, 内核 6.1.99-rockchip-rk3588 | - | ✅ |
| Python | 3.10.12（系统 Python） | - | ✅ |

### 4.3 关键已安装包

| 包 | 版本 | 注意 |
|----|------|------|
| onnxruntime | **1.18.1** | ⚠️ 1.23.2 在 ARM64 导入即崩溃（C++ vector 断言），必须用 1.18.1 |
| numpy | **1.26.4** | ⚠️ 2.x 与 onnxruntime 冲突；opencv 5.0 要求 numpy>=2 但有警告可运行 |
| opencv-python-headless | 5.0.0.93 | 与 numpy 1.26 有版本警告但实际可运行 |
| pyrealsense2 | 2.58.4.10922 | RealSense D430 驱动 |
| foxglove-websocket | 0.1.4 | Foxglove WebSocket 服务端 |
| pymavlink | 2.4.41 | MAVLink 飞控通信 |
| rknnlite2 | **未安装** | PyPI 无此包，需从瑞芯微官方手动安装 |

### 4.4 项目路径（橙Pi5上）

```
/home/orangepi/kswlt_e2d/
├── repo/                    # git clone 的 E2E-RL 分支
├── main.py                  # 飞行主程序（从 repo/deployment/rk3588/main.py 复制）
├── validate_real_depth.py   # 真实深度验证脚本
├── start_flight.sh          # 启动脚本
├── flight.log               # 运行日志
└── test_*.py                # 各种测试脚本
```

**注意**：修改本地 `deployment/rk3588/main.py` 后，必须用 `sftp_put` 上传到橙Pi5覆盖 `~/kswlt_e2d/main.py`，本地 git 和橙Pi5上的代码是分开的。

---

## 5. 飞行主程序 main.py

### 5.1 三种模式

```bash
# ground: 读传感器+跑Policy+Foxglove，不解锁不起飞（最安全）
python3 main.py --mode ground --foxglove-port 8766

# policy: 跑Policy并发送速度指令给飞控（需手动起飞+GUIDED模式）
python3 main.py --mode policy --foxglove-port 8766

# flight: 全自动（自动解锁→起飞→攻击→返航→降落），高风险
python3 main.py --mode flight --foxglove-port 8766 --takeoff-alt 1.5
```

### 5.2 当前运行状态

程序在 **ground 模式**运行，真实深度 + 飞控已连接，Foxglove 在 `ws://100.119.45.114:8766`。

```bash
# 查看日志
tail -f ~/kswlt_e2d/flight.log

# 查看进程
ps aux | grep main.py | grep -v grep

# 停止
pkill -9 -f "python3.*main.py"
```

### 5.3 Foxglove 可视化

- **连接**：Foxglove Studio → Open connection → Foxglove WebSocket → `ws://100.119.45.114:8766`
- **端口**：8766（8765 被 ROS2 foxglove_bridge 占用）
- **7个频道**：
  - `/drone/depth` — 深度图热力图
  - `/drone/pose` — 无人机姿态/位置
  - `/drone/velocity` — 速度向量
  - `/drone/target` — 目标位置
  - `/drone/policy_action` — Policy 加速度输出
  - `/drone/status` — 系统状态文本
  - `/drone/trajectory` — 飞行轨迹

### 5.4 Policy 模式安全机制

- 仅当 `ARMED + GUIDED模式 + 深度OK` 时才发送指令
- 最大速度限制 3 m/s（首次试飞保守值）
- 控制中断时速度指令 0.5s 内衰减到 0
- 切出 GUIDED 模式立即停止发指令
- 程序崩溃 → 飞控 GUIDED 模式自动悬停

---

## 6. 真实深度验证结果（2026-09-16）

用 RealSense D430 真实深度跑了 570 帧 Policy 推理，**全部 sanity check 通过**：

| 指标 | 值 |
|------|-----|
| 相机分辨率 | 640×480 @ 30fps |
| 有效像素比 | 32.0% |
| 平均深度 | 11.54 m |
| Policy 延迟 mean/p95/p99 | 2.87 / 6.51 / 7.75 ms |
| ax（前进加速度） | mean 4.12 m/s²（目标在前方3m，合理） |
| ay（侧向加速度） | mean 0.10 m/s²（目标在正前方，合理） |
| az（垂直加速度） | mean 8.49 m/s²（重力补偿，合理） |

结果文件：`results/real_depth_validation.json`

---

## 7. 训练与仿真（Windows 端）

### 7.1 DiffPhys 训练（WSL2）

```powershell
# 激活 venv 并运行 target-impact 训练
wsl -e bash -c "
  source /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys/venv/bin/activate
  export PATH=/usr/local/cuda-11.8/bin:\$PATH
  cd /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys
  python target_env/train_target_impact.py --num_iters 10000 --batch_size 64
"
```

- WSL venv：`training/diffphys/venv/`（PyTorch 2.2.2+cu118, numpy 1.26.4）
- 上游代码：`training/diffphys/upstream/`（commit 2719361，在 .gitignore）
- 训练 checkpoint：`training/diffphys/results/checkpoints/target_impact_0006k.pth`
- WSL 代理：`http://172.22.0.1:7890`（不是 127.0.0.1）

### 7.2 quadsim_cuda 编译注意事项

1. 必须 `numpy<2`（1.26.4 验证通过），NumPy 2.x 破坏 torch 2.2.2
2. 在 WSL 原生文件系统编译（`~/diffphys_build/`），不要在 /mnt/c（太慢可能挂起）
3. 用 `python setup.py build_ext --inplace`，然后把 .so 复制到 venv site-packages
4. WSL 需要 >8GB RAM，内存不足时 `wsl --shutdown`

### 7.3 Isaac Sim 验证（Windows 原生）

```powershell
# Isaac Python
C:\isaacsim\python.bat -c "print('OK')"

# Headless 评测
powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 100
```

- Isaac Sim 安装路径：`C:\isaacsim\`（6.1.0 standalone）
- 评测结果：`results/policy_eval_1000ep.json`（100% hit）
- 噪声测试：`results/noise_eval_*.json`

---

## 8. 模型规格

| 项 | 值 |
|----|-----|
| 输入 depth | 64×48 → maxpool 4× → 12×16 |
| 输入 state | 10维：local_v(3) + target_body(3) + gravity(3) + margin(1) |
| 网络 | CNN(3层Conv) + GRUCell(192,192) + Linear(192,6) |
| 输出 | 6维 reshape 3×2：accel_body(3) + vel_pred(3) |
| 参数 | 514,496 |
| Depth 归一化 | `x = 3/depth.clamp(0.3,24) - 0.6`，然后 maxpool 4× |
| ONNX | `deployment/onnx/policy.onnx`（35.9KB, opset 18）+ `policy.onnx.data`（2MB，未提交git） |
| 坐标系 | 世界系 ENU，机体系 x=前 y=右 z=上，重力 [0,0,-1] |

---

## 9. 已知问题与限制

### 9.1 硬件相关

1. **D430 在 USB 2.0 端口**：当前插在 Bus 004（480M），虽能跑 640×480@30，但建议换到 USB 3.0（蓝色口）以获得更高帧率/分辨率
2. **ROS2 冲突**：橙Pi5上有 ROS2 Humble 系统，`realsense2_camera` 节点会占用深度相机（只输出红外流，不输出深度）。运行 main.py 前需停止该节点：`kill $(pgrep -f realsense2_camera)`。注意该节点可能被 watchdog 自动重启
3. **飞控 custom_mode 显示异常**：显示 `MODE_50593792`（0x03040000），ArduPilot 模式映射需修正，不影响基本功能
4. **飞控串口偶发报错**：`device reports readiness to read but returned no data`，已加重连逻辑，可能是其他进程访问 /dev/ttyACM0
5. **rknnlite2 未安装**：NPU 推理未测试，当前只用 ONNX CPU（2.87ms 已够用）

### 9.2 算法相关

1. **撞击速度偏低**：0.84 m/s（目标 2-10 m/s），需更多训练或调整 speed_mtp
2. **相机外参未标定**：假设相机光轴=机体前方，无俯角/偏角补偿。真机安装有角度时需在 `configs/rk3588.yaml` 配置外参
3. **yaw 零点未校准**：飞控上电时朝向被当作 yaw=0
4. **margin 是占位值**：state 向量第10维 margin 当前固定 0.2，应从深度图最小值计算
5. **yaw_rate 未实现**：`decode_action` 中 yaw_rate=0，速度预测 vel_pred 未用于转向
6. **撞击恢复（phase 2）未实现**：当前 episode 在 HIT 后立即结束

### 9.3 软件相关

1. **onnxruntime 1.23.2 崩溃**：ARM64 上 C++ std::vector 断言失败，必须用 1.18.1
2. **opencv 5.0 与 numpy 1.26 版本冲突警告**：不影响运行
3. **python3-venv 未安装**：橙Pi5上无法创建虚拟环境，所有包装在用户目录 `~/.local/lib/`

---

## 10. 下一步行动项（按优先级）

### P0: 真机试飞验证
1. 确认试飞场地安全，周围无障碍物
2. 用遥控器手动起飞到 1.5m，切 GUIDED 模式
3. 切换 main.py 到 `--mode policy`，观察 Policy 是否正常控制
4. 在 Foxglove 中监控 vel_cmd 和实际位置
5. 随时切回手动模式接管
6. 记录试飞数据（轨迹、Policy输出、深度图）

### P1: 相机外参标定与配置
1. 测量相机相对飞控 IMU 的安装位置（x/y/z 偏移）
2. 测量相机安装角度（俯角、偏角、滚转角）
3. 在 `configs/rk3588.yaml` 添加 `camera_extrinsics` 配置
4. 在 `inference.py` 和 `main.py` 中应用外参转换
5. 重新验证深度图中心是否对应机体前方

### P2: 提升撞击速度
1. 调整 `train_target_impact.py` 中的 speed_mtp 或速度奖励权重
2. 重新训练 10000+ iters
3. Isaac 验证撞击速度是否达到 2-10 m/s
4. 重新导出 ONNX 并部署到橙Pi5

### P3: RKNN NPU 部署
1. 从瑞芯微官方安装 rknnlite2
2. 用 `deployment/rk3588/export_rknn.py` 转换 ONNX → RKNN
3. 测试 FP32/FP16/INT8 精度差异
4. Benchmark NPU 推理延迟（目标 < 1ms）
5. GRU 若 RKNN 不支持，CPU 执行 GRU + NPU 执行 CNN/MLP

### P4: 完善算法
1. 实现 yaw_rate 控制（从 vel_pred 推导转向）
2. margin 从深度图最小值实时计算
3. 撞击恢复控制器（phase 2）
4. 深度域随机化训练（噪声、丢帧、延迟）
5. 1000ep 真机环境验证（如果安全可行）

---

## 11. 关键文件索引

| 文件 | 作用 |
|------|------|
| `deployment/rk3588/main.py` | 飞行主程序（RealSense + MAVLink + Policy + Foxglove） |
| `deployment/rk3588/inference.py` | RK3588Policy 类（ONNX推理 + 状态构建 + 动作解码） |
| `deployment/rk3588/validate_real_depth.py` | 真实深度算法验证脚本 |
| `deployment/rk3588/export_rknn.py` | RKNN 导出框架 |
| `deployment/onnx/policy.onnx` | ONNX 模型（35.9KB） |
| `deployment/common/export_onnx.py` | PyTorch → ONNX 导出脚本 |
| `training/diffphys/target_env/train_target_impact.py` | 目标撞击训练（7项损失+curriculum） |
| `training/diffphys/upstream/` | DiffPhysDrone 上游代码（commit 2719361） |
| `sim/isaac/` | Isaac Sim 场景/无人机/深度相机/评测完整模块 |
| `configs/` | arena/armor/drone/depth_camera/training/evaluation/rk3588 配置 |
| `scripts/opi5_ssh.py` | 橙Pi5 SSH 封装（paramiko，密码认证） |
| `scripts/opi5_deploy.py` | 橙Pi5部署脚本 |
| `results/real_depth_validation.json` | 真实深度验证结果 |
| `results/policy_eval_1000ep.json` | Isaac 1000ep 评测结果 |
| `docs/CURRENT_STATE.md` | 实时状态 |
| `docs/ARCHITECTURE.md` | 系统架构 |
| `docs/DIFFPHYS.md` | DiffPhys 复现细节 |
| `docs/RK3588_DEPLOYMENT.md` | RK3588 部署指南 |
| `docs/DECISIONS.md` | 技术决策记录 |

---

## 12. 常用命令速查

### Windows 端
```powershell
# 查看橙Pi5飞行日志
python scripts/opi5_ssh.py "tail -20 ~/kswlt_e2d/flight.log"

# 上传文件到橙Pi5
python -c "import sys; sys.path.insert(0,'scripts'); from opi5_ssh import sftp_put; sftp_put('本地路径', '远程路径')"

# 重启橙Pi5飞行程序（ground模式）
python scripts/opi5_ssh.py "pkill -9 -f python3.*main.py; sleep 2; cd ~/kswlt_e2d && nohup python3 -u main.py --mode ground --foxglove-port 8766 > flight.log 2>&1 &"

# Git 提交推送
cd "C:\Users\Admin\Desktop\端到端强化学习无人机仿真"
git add -A && git commit -m "描述" && git push origin E2E-RL
```

### 橙Pi5端（通过SSH执行）
```bash
# 停止 ROS2 RealSense 节点（释放深度相机）
kill $(pgrep -f realsense2_camera)

# 查看 USB 设备速度
lsusb -t

# 查看飞控状态
python3 -c "from pymavlink import mavutil; m=mavutil.mavlink_connection('/dev/ttyACM0',baud=921600); m.wait_heartbeat(); print('OK')"

# 测试 RealSense
python3 /tmp/test_rs.py

# 真实深度验证
cd ~/kswlt_e2d && python3 validate_real_depth.py
```

### WSL2 端
```bash
# 激活训练环境
source /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys/venv/bin/activate
export PATH=/usr/local/cuda-11.8/bin:$PATH
export http_proxy=http://172.22.0.1:7890
export https_proxy=http://172.22.0.1:7890
```

---

## 13. 安全须知

1. **首次真机试飞必须手动起飞**，确认 Policy 输出合理后再切 GUIDED
2. **遥控器随时可接管**：切出 GUIDED 模式程序立即停止发指令
3. **不要在人多或有障碍物的地方试飞**
4. **flight 模式（全自动）风险最高**，建议前两步验证通过后再用
5. **橙Pi5上有 ROS2 系统**，操作时注意不要误删 ROS2 相关文件
6. **不要 force push main/master/d430 分支**
7. **不要删除用户工作目录中的 STL 和图片**，备份在 `C:\RM_E2E_INPUT_BACKUP\`
8. **onnxruntime 不要升级到 1.23.2**，会崩溃

---

*文档更新时间：2026-09-16 | 对应 commit: aa3d21f*
