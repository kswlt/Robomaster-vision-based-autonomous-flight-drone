# D430 Depth Integration — Stage 2 诊断报告（更新版）

> 日期：2026-09-13
> 设备：Orange Pi 5 (RK3588) + Intel RealSense D430 (FW 5.17.3.10)
> **关键结论：D430 固件不支持 IR 和 Depth 同时输出帧**

---

## 1. 测试配置

| 项 | 值 |
|---|---|
| IR profile | 848×480 @ 30 FPS（stereo, Y8） |
| Depth profile（尝试） | 480×270@15, 424×240@6 |
| USB | SuperSpeed 5000M (Bus 02) |
| librealsense | 2.58.3 |
| realsense2_camera | 4.58.3 |

## 2. ROS realsense2_camera 测试结果

### 2.1 启动阶段（前 ~22 秒）
- Open profile 全部成功：Infra(1/2) 848×480@30 + Depth 480×270@15 (Z16)
- Depth topic 正常发布

### 2.2 故障阶段（约 22 秒后）
- 持续报错：**"Frames didn't arrived within 5 seconds"**（每 5 秒一次）
- IR 流完全死锁，VIO 无法初始化（init=0）
- 无 REC/hwmon/USB 错误

### 2.3 回退（关闭 depth）
- IR 立即恢复 848×480@30，VIO 正常（ZUPT accepted, |v|=0.001）

## 3. librealsense 裸测试（绕过 ROS）—— 关键发现

使用最小 C++ 程序（`scripts/test_realsense_combos.cpp`），停止 vio.service 后测试：

| 组合 | Pipeline 启动 | 收到帧数 | 结论 |
|---|---|---|---|
| IR1 only 848×480@30 | ✅ | 15 | 正常 |
| IR2 only 848×480@30 | ✅ | 15 | 正常 |
| IR1+IR2 848×480@30 | ✅ | 15 | 正常 |
| Depth only 480×270@15 | ✅ | 7 | 正常 |
| Depth only 424×240@6 | ✅ | 2 | 正常 |
| **IR1+Depth 848×480@30 + 424×240@6** | ✅ | **0** | **无帧输出** |
| **IR1+IR2+Depth + 424×240@6** | ✅ | **0** | **无帧输出** |
| **IR1+IR2+Depth + 480×270@15** | ✅ | **0** | **无帧输出** |

### 3.1 结论
- **单独开 IR 或单独开 Depth 都正常**
- **同时开 IR+Depth 时，pipeline 启动成功（不报错），但收不到任何帧（0 frames）**
- 这解释了 ROS 中 "Frames didn't arrived within 5 seconds" 的根因
- **这是 D430 固件/硬件限制，不是 ROS wrapper 问题，也不是 USB 带宽问题**
- 降低 depth 分辨率/帧率（424×240@6）也无法解决

## 4. 根因分析

D430 的 IR 和 Depth 共享同一个 Stereo Depth Module。Depth 是设备内部从 IR 计算得出的。在当前固件（5.17.3.10）下，同时启用 IR 输出和 Depth 输出时，设备内部可能发生：
1. Depth 计算阻塞了 IR 帧输出
2. IR 和 Depth 共享缓冲区，导致死锁
3. 固件不支持同时输出原始 IR 和计算后的 Depth

这可能是 D430（而非 D435/D455）的特定限制，因为 D430 是更简化的模块。

## 5. 替代方案（2D Map 深度数据来源）

既然 D430 不能同时输出 IR+Depth，2D Rolling Occupancy Map 的深度数据需要其他来源：

### 方案 A：从 Stereo IR 计算深度（推荐）
- D430 的 IR1/IR2 是已校准的立体相机对
- 用 OpenCV SGBM 或 LIBELAS 计算视差图，转换为深度
- 优点：不影响 VIO，IR 持续输出；可以控制计算帧率（8-15Hz）
- 缺点：需要额外 CPU 计算立体匹配；RK3588 有 NPU/GPU 可加速
- 实现：新增 `stereo_depth_mapper` 节点，输入 IR1+IR2+camera_info，输出 depth image + 2D map

### 方案 B：用 OpenVINS 稀疏点云
- OpenVINS 输出 `/points_msckf`（三角化的 3D 特征点）
- 直接用稀疏点构建 2D Occupancy Grid
- 优点：零额外计算，已有数据
- 缺点：点云稀疏（~100-200 点），可能不够用于避障；特征点集中在纹理丰富区域

### 方案 C：时分复用（不推荐）
- VIO 运行时开 IR，需要建图时切换到 depth
- 缺点：VIO 中断，不可接受

### 方案 D：更新固件（需用户确认）
- 可能新版固件修复了 IR+Depth 同时输出的问题
- 风险：固件更新可能丢失校准，需用户确认

## 6. 当前决策

**推荐方案 A：从 Stereo IR 计算深度。**

理由：
1. 不影响 VIO（IR 持续 30Hz 输出）
2. RK3588 有足够算力（6 核 CPU + Mali GPU + NPU）
3. 可以控制深度计算帧率（8-15Hz），满足 2D Map 需求
4. 不需要额外硬件

下一步：实现 `stereo_depth_mapper` 节点（Stage 3 调整为基于 IR 立体匹配的深度建图）。

## 7. 相关文件

| 文件 | 说明 |
|---|---|
| scripts/test_realsense_combos.cpp | 流组合兼容性裸测试 |
| scripts/test_realsense_depth_ir.cpp | IR+Depth 同时开启测试 |
| start_vio_systemd.sh | 当前 depth 关闭（enable_depth:=false） |
| docs/D430_848x480_30_BASELINE.md | Stage 1B 相机+VIO 静态基线 |
