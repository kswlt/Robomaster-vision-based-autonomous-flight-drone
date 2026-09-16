# RK3588 实机部署指南

## 1. 整体架构

```
┌─────────────────────────────────────────────────────┐
│                   RK3588 (计算板)                     │
│                                                      │
│  ┌──────────┐   ┌───────────┐   ┌────────────────┐  │
│  │ 深度相机  │──▶│ 预处理     │──▶│ CNN+GRU Policy │  │
│  │ (USB/MIPI)│   │ 64x48     │   │ NPU/CPU 推理   │  │
│  └──────────┘   │ 逆深度归一化│   └───────┬────────┘  │
│                 └───────────┘           │           │
│                                         ▼           │
│  ┌──────────┐   ┌───────────┐   ┌────────────────┐  │
│  │ 飞控IMU   │──▶│ 状态向量   │──▶│ 动作解码       │  │
│  │ (串口/CAN)│   │ 10-dim    │   │ accel+yaw_rate │  │
│  └──────────┘   └───────────┘   └───────┬────────┘  │
│                                         │           │
│                                         ▼           │
│                                 ┌────────────────┐  │
│                                 │ 飞控接口        │  │
│                                 │ MAVLink/串口    │  │
│                                 └───────┬────────┘  │
└─────────────────────────────────────────┼───────────┘
                                          │
                                          ▼
                                 ┌────────────────┐
                                 │ 飞控 (姿态/电机) │
                                 └────────────────┘
```

**职责划分**：
- **RK3588**：深度预处理、Policy 推理、目标信息处理、装甲板视觉检测
- **飞控**：姿态稳定、底层控制环、电机输出
- **比赛现场不训练**，只推理

---

## 2. 硬件清单

| 组件 | 推荐型号 | 接口 | 说明 |
|------|----------|------|------|
| 计算板 | RK3588 (8GB RAM) | - | 瑞芯微，6 TOPS NPU |
| 深度相机 | Orbbec Femto Mega / RealSense D435i | USB 3.0 | 全局快门，深度+IMU |
| 飞控 | Pixhawk 6C / CUAV V5+ | UART (TELEM2) | PX4/ArduPilot |
| 数传 | 可选 | UART | 调试用 |
| 电池 | 4S/6S LiPo | - | 给 RK3588 用 BEC 5V/3A |

**接线**：
- 深度相机 → RK3588 USB 3.0
- 飞控 TELEM2 → RK3588 UART (GPIO 8/10 或 USB 转 TTL)
- RK3588 供电 → 5V/3A BEC

---

## 3. 系统镜像与依赖

### 3.1 RK3588 系统
推荐使用 **Ubuntu 22.04 for RK3588**（官方或友善之臂）。

```bash
# 基础依赖
sudo apt update && sudo apt install -y \
    python3-pip python3-dev python3-opencv \
    cmake build-essential git \
    libusb-1.0-0-dev libgl1-mesa-glx \
    serialport-utils

# Python 依赖
pip3 install numpy opencv-python pyserial onnxruntime
```

### 3.2 RKNN Toolkit2 (NPU 推理)
```bash
# 在 RK3588 上安装运行时
pip3 install rknnlite2

# 验证
python3 -c "from rknnlite.api import RKNNLite; print('RKNN Lite OK')"
```

### 3.3 深度相机驱动
```bash
# Orbbec Femto Mega
sudo apt install -y libuvc-dev
pip3 install pyorbbecsdk

# 或 RealSense
sudo apt install -y librealsense2-utils
pip3 install pyrealsense2
```

---

## 4. 模型导出流程

### 4.1 PC 端：PyTorch → ONNX
```powershell
# 在 Windows PC 上
cd C:\Users\Admin\Desktop\端到端强化学习无人机仿真
C:\isaacsim\python.bat deployment\common\export_onnx.py
```
输出：`deployment/onnx/policy.onnx` (35.9 KB)

### 4.2 PC 端：ONNX → RKNN
```bash
# 在 WSL2 或 Linux 上安装 RKNN Toolkit2
pip3 install rknn-toolkit2

# 转换
python3 deployment/rk3588/export_rknn.py \
    --onnx deployment/onnx/policy.onnx \
    --output deployment/rk3588/policy.rknn \
    --quantize none  # 先用 FP16，INT8 需校准
```

### 4.3 量化对比（必须做）
| 精度 | 模型大小 | 推理延迟 | 命中率影响 |
|------|----------|----------|-----------|
| FP32 | ~36 KB | 基准 | 基准 |
| FP16 | ~18 KB | ↓40% | <1% |
| INT8 | ~9 KB | ↓60% | 需校准，可能下降 |

**INT8 量化不能默认开启**，必须用真实深度图做校准集，对比命中率后再决定。

---

## 5. RK3588 推理服务

### 5.1 核心推理循环
```python
from deployment.rk3588.inference import RK3588Policy

policy = RK3588Policy("policy.rknn", use_npu=True)
policy.reset()

while running:
    # 1. 读取深度图 (64x48 or higher, will be resized)
    depth = camera.get_depth()  # meters, float32

    # 2. 读取飞控状态
    pos, vel, yaw = flight_controller.get_state()

    # 3. 目标位置（来自装甲板检测或预设）
    target = get_armor_target()

    # 4. Policy 推理 (~10ms on NPU)
    action = policy.infer(depth, pos, vel, yaw, target)
    # action = {"accel": [ax,ay,az], "yaw_rate": float, "latency_ms": float}

    # 5. 发送给飞控
    flight_controller.send_accel_target(action["accel"])
    flight_controller.send_yaw_rate(action["yaw_rate"])
```

### 5.2 状态机（任务级）
```
TAKEOFF → ATTACK → HIT → RECOVER → RETURN → HOME
```
- **TAKEOFF/RETURN**：用脚本控制器（定高悬停/返航）
- **ATTACK**：Policy 控制，目标=ArmorTarget
- **HIT**：碰撞检测触发，记录撞击速度/角度
- **RECOVER**：撞击后姿态恢复控制器

状态机不是 AI，是 Python 逻辑。

---

## 6. 飞控接口 (MAVLink)

### 6.1 连接
```python
from pymavlink import mavutil

master = mavutil.mavlink_connection('/dev/ttyS0', baud=921600)  # UART
# 或 USB: '/dev/ttyUSB0'
master.wait_heartbeat()
```

### 6.2 读取状态
```python
msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True)
pos = [msg.x, msg.y, -msg.z]  # NED → ENU

msg = master.recv_match(type='ATTITUDE', blocking=True)
yaw = msg.yaw

msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True)
vel = [msg.vx, msg.vy, -msg.vz]
```

### 6.3 发送控制（加速度指令 → OFFBOARD 模式）
```python
def send_accel_target(master, accel, yaw_rate):
    # SET_POSITION_TARGET_LOCAL_NED with acceleration only
    master.mav.set_position_target_local_ned_send(
        0, master.target_system, master.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b0000011111000111,  # accel + yaw_rate bits
        0, 0, 0, 0, 0, 0,     # pos, vel (ignored)
        accel[0], accel[1], accel[2],  # accel
        yaw_rate, 0)          # yaw_rate, yaw (ignored)
```

### 6.4 模式切换
```python
# 切 OFFBOARD
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
    6, 0, 0, 0, 0, 0)  # 6 = OFFBOARD

# 解锁
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
    1, 0, 0, 0, 0, 0, 0)
```

---

## 7. 深度相机接入

### 7.1 Orbbec Femto Mega
```python
from pyorbbecsdk import Pipeline, Config, OBFormat

pipeline = Pipeline()
config = Config()
config.set_align_mode(OBAlignMode.HW_ALIGN_D2C)
pipeline.enable_stream(OBFormat.OB_FORMAT_Y16, 640, 480, 30)
pipeline.start(config)

def get_depth():
    frames = pipeline.wait_for_frames(1000)
    depth_frame = frames.get_depth_frame()
    data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
    depth = data.reshape(480, 640).astype(np.float32) / 1000.0  # mm → m
    return depth  # 480x640, meters
```

### 7.2 深度预处理（在 RK3588 上）
```python
import cv2

def preprocess_depth(depth_raw):
    # 1. Resize to 64x48 (Policy input)
    depth_small = cv2.resize(depth_raw, (64, 48), interpolation=cv2.INTER_NEAREST)
    # 2. 归一化由 RK3588Policy.normalize_depth() 完成
    return depth_small
```

---

## 8. 装甲板目标检测（可选）

如果目标位置不固定，需要视觉检测装甲板：
- **轻量方案**：OpenCV 颜色阈值 + 轮廓检测（红色/蓝色灯条）
- **模型方案**：YOLOv8n 量化到 RKNN（~10ms）
- 输出：目标在相机坐标系中的 3D 位置 → 转换到世界坐标系

检测频率可以低于 Policy（10Hz 检测，30Hz 推理，中间帧用预测）。

---

## 9. 启动脚本

### 9.1 systemd 服务（开机自启）
```ini
# /etc/systemd/system/e2e-drone.service
[Unit]
Description=E2E-RL Drone Policy Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/rock/e2e-drone
ExecStart=/usr/bin/python3 main.py --model policy.rknn --npu
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable e2e-drone
sudo systemctl start e2e-drone
sudo journalctl -u e2e-drone -f  # 查看日志
```

### 9.2 主程序 main.py
```python
import argparse, signal, sys
from deployment.rk3588.inference import RK3588Policy

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="policy.rknn")
    parser.add_argument("--npu", action="store_true")
    parser.add_argument("--takeoff-alt", type=float, default=1.5)
    args = parser.parse_args()

    # 初始化
    camera = DepthCamera()
    fc = FlightController("/dev/ttyS0", 921600)
    policy = RK3588Policy(args.model, use_npu=args.npu)

    # Benchmark
    bench = policy.benchmark(100)
    print(f"Policy: {bench['fps']:.1f} FPS, {bench['mean_ms']:.1f}ms avg")

    # 状态机
    state = "IDLE"
    running = True

    def shutdown(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, shutdown)

    while running:
        depth = camera.get_depth()
        pos, vel, yaw = fc.get_state()

        if state == "IDLE":
            state = "TAKEOFF"
        elif state == "TAKEOFF":
            if pos[2] >= args.takeoff_alt:
                state = "ATTACK"
                policy.reset()
            fc.send_velocity([0, 0, 1.0])
        elif state == "ATTACK":
            target = get_target()  # 装甲板位置
            action = policy.infer(depth, pos, vel, yaw, target)
            fc.send_accel_target(action["accel"], action["yaw_rate"])
            if check_hit(pos, target):
                state = "RETURN"
        elif state == "RETURN":
            fc.send_velocity(home_direction(pos) * 2.0)
            if dist_to_home(pos) < 0.5:
                state = "LAND"
        elif state == "LAND":
            fc.send_velocity([0, 0, -0.5])
            if pos[2] < 0.1:
                fc.land()
                break

    fc.disconnect()
    camera.stop()

if __name__ == "__main__":
    main()
```

---

## 10. 性能预期

| 指标 | NPU (RKNN) | CPU (ONNX) |
|------|-----------|------------|
| 推理延迟 | ~8-12 ms | ~30-50 ms |
| FPS | 80-120 | 20-33 |
| CPU 占用 | <10% | ~200% (4核) |
| NPU 占用 | ~30% | 0% |
| 内存 | ~50 MB | ~100 MB |

**GRU 处理**：
- RKNN 对 GRU 支持良好 → 全部上 NPU
- 若遇到兼容性问题 → CNN/MLP 上 NPU，GRU 用 ARM CPU（~2ms）

---

## 11. 调试与验证

### 11.1 单机推理测试（不接飞控）
```bash
python3 -m deployment.rk3588.benchmark --model policy.rknn --npu
```

### 11.2 深度相机测试
```bash
python3 tools/test_camera.py  # 显示深度图，保存样本
```

### 11.3 飞控通信测试
```bash
python3 tools/test_flight_controller.py  # 读取姿态/位置，发送模拟指令
```

### 11.4 安全开关
- **物理开关**：遥控器切飞控模式 → 立即接管
- **软件看门狗**：RK3588 超过 100ms 不发指令 → 飞控自动悬停
- **紧急降落**：检测到异常 → 自动降落

---

## 12. 部署检查清单

- [ ] RK3588 系统刷好，SSH 可连
- [ ] 深度相机驱动安装，深度图正常
- [ ] 飞控串口连接，MAVLink 通信正常
- [ ] `policy.rknn` 拷贝到板子
- [ ] NPU 推理 benchmark 通过（>30 FPS）
- [ ] 状态机逻辑测试（模拟数据）
- [ ] 手动模式试飞（不接 Policy）
- [ ] OFFBOARD 模式 + 脚本控制器试飞
- [ ] Policy 推理 + 飞控联调（低速）
- [ ] 完整任务：起飞→撞击→返航
- [ ] 安全开关验证
