# D430 Depth Integration — Stage 2 诊断报告

> 日期：2026-09-13
> 设备：Orange Pi 5 (RK3588) + Intel RealSense D430
> 状态：**Depth 开启导致 IR 流死锁，已回退为 depth 关闭**

---

## 1. 测试配置

| 项 | 值 |
|---|---|
| IR profile | 848×480 @ 30 FPS（stereo, Y8） |
| Depth profile | 480×270 @ 15 FPS（Z16） |
| USB | SuperSpeed 5000M (Bus 02) |
| librealsense | 2.58.3 |
| realsense2_camera | 4.58.3 |
| launch 参数 | `enable_depth:=true depth_module.depth_profile:=480x270x15` |

## 2. 测试结果

### 2.1 启动阶段（前 ~22 秒）
- Open profile 全部成功：
  - Infra(1): 848×480 @ 30 ✅
  - Infra(2): 848×480 @ 30 ✅
  - Depth(0): 480×270 @ 15 (Z16) ✅
- RealSense Node Is Up ✅
- Depth topic 正常发布（/camera/camera/depth/image_rect_raw）

### 2.2 故障阶段（约 22 秒后）
- 出现持续报错：**"Frames didn't arrived within 5 seconds"**（每 5 秒一次）
- IR 流完全死锁（ros2 topic hz 无输出）
- Depth 流看似仍在发布（~30Hz），但 IR 已停止
- OpenVINS 无法初始化：`init=0 init_time=-1.000`
- VIO odom 不发布
- 无 REC error，无 hwmon error，无 USB reset

### 2.3 回退阶段（关闭 depth 后）
- `enable_depth:=false`，重启服务
- IR 流立即恢复：848×480 @ 30 ✅
- "Frames didn't arrived" 计数 = 0 ✅
- OpenVINS 初始化正常：ZUPT accepted, |v|=0.001, chi2=0.731 ✅
- vio_bridge 正常发送 VISION_POSITION_ESTIMATE，EKF 正常 ✅

## 3. 前后对比

| 指标 | Depth 关闭（正常） | Depth 开启（故障） |
|---|---|---|
| Infra1 帧率 | 30 Hz 稳定 | 死锁（0 Hz） |
| Infra2 帧率 | 30 Hz 稳定 | 死锁 |
| Depth 帧率 | — | ~30 Hz（异常） |
| Frame timeout | 0 | 持续（每 5 秒） |
| VIO 初始化 | 正常（ZUPT accepted） | init=0，无法初始化 |
| VIO odom | 147 Hz 发布 | 不发布 |
| REC/hwmon error | 0 | 0 |

## 4. 可能原因分析

### 4.1 最可能：realsense2_camera 的 IR+Depth 同步问题
D430 的 IR 和 Depth 共享同一个 Stereo Depth Module。Depth 是设备内部从 IR 计算得出的，理论上不需要额外 USB 带宽。但 realsense2_camera 在同时发布 IR1+IR2+Depth 时，可能存在帧同步或缓冲区管理问题，导致 IR 流死锁。

### 4.2 Depth profile 兼容性
480×270@15 可能不是 D430 的标准 depth profile，或者与 848×480@30 IR 组合不兼容。D430 的标准 depth profile 通常是 848×480、640×480、424×240 等。

### 4.3 固件/硬件问题
D430 固件 5.17.3.10 在同时开启 IR+Depth 时可能存在已知 bug。

### 4.4 供电问题
Depth 开启后设备功耗增加，可能导致供电不足（虽然用户已解决供电问题，但同时开更多流可能仍有边际影响）。

## 5. 后续排查计划

### 5.1 用 librealsense 裸测试（排除 ROS wrapper）
写最小 C++ 程序，同时开启 IR1+IR2+Depth，运行 60 秒，观察是否出现帧丢失。如果裸测试正常，说明是 realsense2_camera 的问题；如果裸测试也失败，说明是固件/硬件问题。

### 5.2 尝试不同的 depth profile
- 424×240 @ 6（最低 profile，最不可能导致带宽问题）
- 640×480 @ 6
- 848×480 @ 6
- 关闭 IR2，只开 IR1+Depth（减少流数量）

### 5.3 检查 D430 depth+IR 同时运行的官方支持
查阅 Intel RealSense 文档，确认 D430 是否支持同时发布 IR 和 Depth（某些配置下 depth 会替代 IR 输出）。

### 5.4 更新固件（需用户确认）
当前固件 5.17.3.10。如果有更新版本，可能修复了 IR+Depth 同时运行的 bug。但固件更新有风险，需用户确认后执行。

## 6. 当前决策

**按任务原则：VIO > Depth > Mapping。不能为了地图牺牲 VIO。**

当前保持 `enable_depth:=false`，确保 VIO 稳定运行。Depth 集成的后续排查在 VIO baseline 完全验证后进行。

如果后续 2D Map 需要 depth，可以考虑：
1. 用 IR 视差直接计算深度（不依赖 depth stream）
2. 只在需要建图时短暂开启 depth，建图完成后关闭
3. 排查并修复 IR+Depth 同时运行的问题

## 7. 相关文件

| 文件 | 说明 |
|---|---|
| start_vio_systemd.sh | 当前 depth 关闭（enable_depth:=false） |
| docs/D430_848x480_30_BASELINE.md | Stage 1B 相机+VIO 静态基线 |
| docs/REALSENSE_HWMON_REC_ERROR_DIAGNOSIS.md | 排线故障根因分析 |
