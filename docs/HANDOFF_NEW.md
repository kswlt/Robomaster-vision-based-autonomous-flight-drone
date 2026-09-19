# E2E-RL 无人机项目交接文档

> 新 Agent 读完本文档即可接手。所有信息截至 2026-09-20。

---

## 1. 项目概述

用 **RealSense D430 深度相机 + 端到端强化学习策略（ONNX）** 在橙 Pi5（RK3588）上实现无人机自主避障飞行。飞控是 PX4，通过 MAVLink OFFBOARD 模式控制。

**当前可工作的系统**：手动起飞 → 网页按钮触发 → PX4 OFFBOARD 加速度控制 → 真实深度 + Policy 避障飞行。

**下一步开发方向**：用 D430 识别 ArUco tag 实现自动降落 + 精准悬停。

---

## 2. 硬件清单

| 部件 | 型号 | 说明 |
|------|------|------|
| 机载计算机 | 橙 Pi5 (Orange Pi 5) | RK3588, 8GB RAM, Ubuntu 22.04 |
| 飞控 | MicoAir743AIO | PX4 固件，USB 连接 |
| 深度相机 | RealSense D430 | USB 3.0，深度 + 红外 |
| 遥控器 | 标准遥控器 | 手动起降用 |

---

## 3. 连接板子

### SSH 连接
```bash
# 局域网（推荐，快）
ssh orangepi@192.168.1.215
# 密码: orangepi

# Tailscale（备用）
ssh orangepi@100.119.45.114
# 密码: orangepi
```

### Windows 本地 SSH 封装
项目自带 `scripts/opi5_ssh.py`（paramiko）：
```python
import sys; sys.path.insert(0, 'scripts')
from opi5_ssh import connect, sftp_put, run
c = connect()
code, out, err = run("ls ~/kswlt_e2d/")
print(out)
sftp_put('local/file.py', '/home/orangepi/kswlt_e2d/file.py')
```

HOST 默认写死为 `100.119.45.114`（Tailscale），局域网用 `192.168.1.215`。

### 从 Windows 上传文件后必须验证
板子上 sftp 偶尔会损坏文件，上传后**必须**验证：
```bash
python3 -c "import py_compile; py_compile.compile('/home/orangepi/kswlt_e2d/web_vis.py', doraise=True)"
```

---

## 4. 板子关键路径

| 路径 | 说明 |
|------|------|
| `~/kswlt_e2d/web_vis.py` | 主程序（浏览器 dashboard + 避障控制） |
| `~/kswlt_e2d/upstream_avoidance.onnx` | 避障策略模型 |
| `~/kswlt_e2d/upstream_avoidance.onnx.data` | ONNX 外部数据 |
| `~/kswlt_e2d/web_vis.log` | 运行日志 |
| `/home/orangepi/kswlt/` | VIO 系统（ROS2，已禁用自启） |
| `/dev/ttyACM0` | PX4 飞控串口 @ 921600 |

本地对应路径：`deployment/rk3588/web_vis.py`

---

## 5. 启动端到端飞行系统

### 每次板子重启后必须做的事
1. **停掉 VIO**（会自动占相机）：
```bash
echo orangepi | sudo -S systemctl stop vio.service watchdog_camera.service vio-watchdog.service
echo orangepi | sudo -S pkill -9 -f realsense2_camera
```

2. **启动 web_vis**（后台运行）：
```bash
cd ~/kswlt_e2d
setsid bash -c 'python3 -u web_vis.py > web_vis.log 2>&1' < /dev/null & disown
```

3. **验证启动成功**：
```bash
sleep 6
curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:8080/
tail -5 ~/kswlt_e2d/web_vis.log
```
看到 `HTTP 200` 和 `[LOOP] frame=100 fps=30` 就是成功。

### 访问 Dashboard
浏览器打开：`http://192.168.1.215:8080`

**必须 Ctrl+Shift+R 强制刷新**（服务器已加 no-cache 头，但偶尔需要手动刷）。

### Windows 一键脚本
```powershell
cd "C:\Users\Admin\Desktop\端到端强化学习无人机仿真"
python scripts/start_e2e.py        # 停 VIO + 启动 web_vis
python scripts/check_wv.py        # 检查状态
python scripts/push_restart.py    # 上传本地 web_vis.py + 重启
```

---

## 6. 飞行操作流程

1. **遥控器手动起飞**到安全高度（1.5-2m），保持 POSCTL 模式悬停
2. 确认 dashboard 显示"真实深度"、遥测数据正常
3. 点击 **"开始自动避障"** 按钮
4. 飞机切到 OFFBOARD，**自动一直往前飞 + 避障**（胡萝卜模式：目标点永远在前方 5m）
5. 停止：点"停止自动控制"或遥控器切回手动

**安全约束**：
- 不自动起飞，必须手动起飞后触发
- 不修改任何 PX4 参数
- 不用 GPS
- 高度定高（端到端不控制 Z）
- 速度上限 1.0 m/s，加速度限幅 ±1.5 m/s²

---

## 7. 当前代码配置（已部署到板子）

### 加速度控制
- **加速度限幅**：`np.clip(net_accel_neu, -1.5, 1.5)`
- **速度上限**：`MAX_SPEED = 1.0` m/s
- **OFFBOARD type_mask**：`0b0000110100111111`（忽略 Z 加速度 = 定高）
- **相机方向翻转**：相机装反了 180°，代码中 `accel_body[0] *= -1; accel_body[1] *= -1`

### Policy 输入输出
- 输入：12×16 深度图（maxpool）+ 10 维状态（局部速度3 + 目标速度3 + up向量3 + margin1）
- 输出：6 维（加速度3 + 预测速度3）
- GRU 隐藏状态：192 维，每帧自动更新

### 胡萝卜模式
自动飞行时，目标点每帧刷新为当前位置 + 机头方向 × 5m，所以飞机一直往前飞。

---

## 8. 环境约束（板子上）

| 包 | 版本 | 原因 |
|---|---|---|
| onnxruntime | 1.18.1 | 1.23.2 在 ARM64 崩溃 |
| numpy | 1.26.4 | 2.x 与 onnxruntime 1.18 冲突 |
| Python | 3.10 | 系统自带 |

**不要升级这些包。**

---

## 9. VIO 系统（已禁用）

橙 Pi5 上原有一套 VIO（视觉惯性里程计）系统，会自动占相机：
- 服务：`vio.service`, `watchdog_camera.service`, `vio-watchdog.service`
- 已 `systemctl disable`，但重启后可能被其他 watchdog 拉起
- **每次启动 web_vis 前必须先停掉**

---

## 10. Dashboard 面板说明

| 面板 | 显示内容 |
|------|---------|
| 深度相机 | RealSense D430 真实深度图（暖色=近，冷色=远） |
| 遥测数据 | 位置、高度、航向角、速度、帧率、电压、深度有效率 |
| 自动避障控制 | 开始/停止按钮、目标点设置 |
| Policy 净加速度指令 | 发给飞控的加速度（AX/AY/AZ），限幅 ±1.5 |
| Policy 加速度输出 | 模型原始输出（未限幅） |
| 飞行指令 | 箭头可视化（橙=指令方向，绿=实际方向）+ 指令速度 |
| 实际指令 | 大白话描述："前进、左移 1.50 m/s²，定高" |
| 飞行轨迹 | 俯视图轨迹图 |

---

## 11. 已知坑

1. **PowerShell Set-Content 会损坏 UTF-8 文件**——改代码用 Python 脚本读写
2. **sftp_put 上传后文件可能损坏**——上传后必须 `py_compile` 验证
3. **浏览器缓存**——改完 JS 必须 Ctrl+Shift+R 强刷
4. **VIO 自启**——disable 了但重启后可能被拉起，每次先 stop
5. **setsid 启动命令会超时**——这是正常的（后台进程不返回），单独验证 HTTP 200 即可
6. **uvcvideo 是内核内置模块**——无法 modprobe -r，相机问题靠重新插拔/换口解决

---

## 12. 下一步开发：Tag 识别自动降落/悬停

### 需要做的
1. **ArUco tag 检测**：用 D430 彩色/深度流检测 ArUco marker
2. **tag 位姿估计**：从 tag 大小和深度计算相对位置
3. **降落控制**：检测到 tag 后，OFFBOARD 切换到位置控制，飞向 tag 上方
4. **精准悬停**：在 tag 上方保持位置

### 建议的代码结构
- 在 `web_vis.py` 中新增 tag 检测线程（和深度流并行）
- 复用现有的 PX4 OFFBOARD 控制通道
- 新增 dashboard 面板显示 tag 检测状态和相对位置
- 新增"Tag 降落"按钮触发降落模式

### 注意
- D430 彩色流当前未启用（`enable_color:=false`），需要在 realsense 配置中打开
- 降落时需要控制 Z 轴加速度（当前 type_mask 忽略了 Z，需要改回全轴控制）
- tag 检测用 OpenCV ArUco 模块（`cv2.aruco`）

---

## 13. Git 仓库

```
origin: https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone
```

主分支 main。提交前清理临时脚本（scripts/ 下大量 _check/_debug 临时文件）。
