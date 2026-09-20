# E2E-RL 无人机系统交接文档

> 更新时间：2026-09-20
> 板子：橙 Pi 5 (RK3588)，IP `192.168.1.215`

## 1. 系统概述

端到端强化学习无人机避障 + ArUco Tag 自动降落 + 键盘遥控系统。

- **飞控**：PX4 MicoAir743AIO，`/dev/ttyACM0` @ 921600
- **相机**：RealSense D430（深度 + IR 流）
- **机载电脑**：Orange Pi 5 (RK3588)，Ubuntu
- **策略模型**：DiffPhys 上游避障策略 `upstream_avoidance.onnx`（Nature Machine Intelligence 2025）
- **控制方式**：PX4 OFFBOARD（加速度/速度控制），定高模式

## 2. SSH 连接

```bash
ssh orangepi@192.168.1.215
# 密码：orangepi
```

关键路径：
- 主程序：`~/kswlt_e2d/web_vis.py`
- ONNX 模型：`~/kswlt_e2d/upstream_avoidance.onnx` + `.data`
- 日志：`~/kswlt_e2d/web_vis.log`
- CSV 记录：`~/kswlt_e2d/debug_log.csv`
- Dashboard：`http://192.168.1.215:8080`

本地封装脚本：`scripts/opi5_ssh.py`（paramiko）

## 3. 启动流程

```bash
# 1. 停 VIO（会占相机）
echo orangepi | sudo -S systemctl stop vio.service watchdog_camera.service vio-watchdog.service
echo orangepi | sudo -S pkill -9 -f realsense2_camera

# 2. 启动主程序
cd ~/kswlt_e2d
nohup python3 -u web_vis.py > web_vis.log 2>&1 &

# 3. 验证
sleep 8
curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:8080/
```

VIO 已永久 disable（`systemctl disable`），但重启后需确认未自启。

## 4. 飞行模式

Dashboard 有三种控制模式（互斥）：

| 模式 | 按钮 | 控制方式 | 说明 |
|------|------|---------|------|
| 手动 | 遥控器 | POSCTL | 手动起飞/降落 |
| 自动避障 | ▶ 开始自动避障 | OFFBOARD 加速度 | 端到端 RL 避障，定高 |
| Tag 降落 | 🎯 开始 Tag 降落 | OFFBOARD 速度 | ArUco 搜索→对齐→下降 |
| 键盘遥控 | 开始键盘控制 | OFFBOARD 速度 | WASD + 空格/Q |

### 操作流程
1. 遥控器手动起飞到 1.5-2m，保持 POSCTL 悬停
2. 点"开始自动避障"→ RL 带飞
3. 或点"开始键盘控制"→ WASD 遥控
4. 或点"Tag 降落"→ 自动搜索 Tag 并降落
5. 紧急情况切遥控器手动

## 5. Dashboard 面板

- 深度相机（暖色=近，冷色=远，Policy 输入 12x16 maxpool）
- 彩色流 + Tag 检测（IR 流，ArUco 叠加图）
- 遥测数据（位置、速度、航向、电池）
- 自动避障控制
- Tag 自动降落
- **键盘遥控**（WASD + 空格/Q，0.5 m/s）
- **净加速度指令（发给飞控）** — AX/AY/AZ 三条 ±1.5 m/s²
- **Policy 加速度输出（原始）** — AX/AY/AZ 三条原始模型输出
- 飞行指令（箭头 + 速度读数）
- 飞行轨迹俯视图
- 实际指令（大白话描述）
- 运行状态

## 6. 当前参数

| 参数 | 值 | 说明 |
|------|---|------|
| 加速度限幅 | ±1.5 m/s² | 净加速度 |
| 速度上限 | 1.0 m/s | 速度限制器 |
| OFFBOARD type_mask | `0b0000110100111111` | 定高（忽略 Z 加速度） |
| 相机翻转 | accel_body[0,1] *= -1 | 代码第 697-698 行 |
| 安全刹车 | marg < 0.35m 切断前向 | 防撞墙 |
| 胡萝卜模式 | 目标点每帧刷新到前方 5m | 一直往前飞 |
| IR 投影器 | 已关闭 | 消除斑点干扰 ArUco |
| Tag 字典 | DICT_4X4_50 | marker 15cm |
| Tag 保持 | 0.5s 时间滤波 | 防闪烁 |
| 键盘速度 | 0.5 m/s | WASD |

## 7. 关键代码位置

- Policy 推理：`policy.infer(depth, pos, vel, yaw, target)` → accel_body, vpred_body
- 控制律：`net_accel = accel_world - vpred_world`（重力抵消）
- 安全刹车：主循环中 `closest < 0.35m` 切断前向
- Tag 检测：`TagDetector` 类，IR 流 + CLAHE + morphology + ArUco
- 键盘控制：`/key_start`, `/key_stop`, `/key_update` POST 接口

## 8. 环境约束

- onnxruntime 必须 **1.18.1**
- numpy 必须 **1.26.4**
- OpenCV 5.0.0（ArUco 用新 API `ArucoDetector`）
- Python 3.x

## 9. 已知问题

1. **Tag 检测闪烁**：IR 图像上 ArUco 偶尔丢帧，已加 0.5s 保持窗口
2. **Z 轴加速度**：模型一直输出 abz≈-1.2，定高模式 PX4 忽略，不影响
3. **对着墙直冲**：模型不减速，靠安全刹车切断前向
4. **sftp 上传后文件可能损坏**：上传后需 `py_compile` 验证
5. **PowerShell Set-Content 损坏 UTF-8**：用 Python 脚本改代码
6. **浏览器需 Ctrl+Shift+R 强刷**

## 10. Git 仓库

- 地址：`https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone`
- 分支：`E2E-RL`
- 板子上的 `web_vis.py` 已含 Tag 降落 + 键盘遥控功能

## 11. 用户约束

- 不改飞控参数
- 不自动起飞
- 不用 GPS
- 全中文界面
- 高度定高（用光流高度）
