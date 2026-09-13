# REALSENSE HWMON / REC ERROR DIAGNOSIS — D430/D4 链路故障

> 状态：**根因确认 = module↔board 排线（interposer）接触不良**；修复后 Stage 1A PASS
> 日期：2026-09-13
> 设备：RealSense **D430**（PID 0x0AD4）@ OrangePi5 (RK3588)

---

## 0. 根因结论（已确认）

**module 与 board 之间的排线（interposer/连接器）接触不良**，导致：
- 设备被错误识别为 D400（PID 0x0AD1，fallback 身份），正确身份为 **D430（PID 0x0AD4）**
- EEPROM/校准数据读取失败 → module serial 读到 `ffffffffffff`、Recommended FW 读不到
- Depth Units 无法读取 → `hwmon command 0x2c (GET_ADV) failed (-9)`
- 所有 stream 启动失败（REC error / Error starting device）

**修复**：重新插好排线后（用户操作），全部恢复。

## 1. 修复前后对比（实测）

| 项 | 排线脱落（故障态） | 排线修复（正常态） |
|---|---|---|
| PID / 型号 | 0x0AD1 = D400（fallback） | **0x0AD4 = D430** ✅ |
| Device Name | RealSense D400 | **RealSense D430** |
| module Serial | ffffffffffff | **938422073656** |
| Depth Units(28) | FAIL (hwmon 0x2c -9) | **min=1e-06 max=0.01 def=0.001 OK** |
| Laser Power(13) | not supported | **min=0 max=360 def=150 OK** |
| Enable Auto WB(11) | OK | not supported（D430 无 RGB，正常） |
| Stream 启动 | 全部 FAIL (0x2c -9) | **Test A-E 全部 PASS** |
| USB | SuperSpeed 5000M（Bus 02） | 重插后误插 USB2.0（Bus 04, 480M）⚠️ |

**结论**：D430 模组本身无损坏；排线接触不良是全部症状的根因。`Recommended FW not supported` 为该固件正常行为（不影响功能）。

## 2. 当前遗留问题：USB2.0 端口限制 848×480@30

排线修复后相机被插到 **USB2.0 口（Bus 04, ehci 480M）**，导致：
- librealsense 在 USB2 下 **不暴露 848x480@30 profile**（仅 848x480@10/8/6；640x480@30 存在）
- realsense2_camera 报 `Given value 848x480x30 is invalid` → 回退 640x480@15
- VIO 虽恢复运行（ZUPT 正常），但分辨率受限

**解决**：把相机 USB 插回 **USB3 SuperSpeed 口（Bus 02, 5000M）**，重启 vio.service。
（USB3 下 profile 完整：848x480@90/60/30/15/6 全存在——已在故障态 D400 枚举中证实）

## 3. 故障诊断过程总结

```
症状：D430 无法启动任何 stream，hwmon 0x2c (GET_ADV) -9，REC error
  ↓
1. USB 枚举正常（SuperSpeed、ASIC serial 正常）→ 排除链路断
2. 最小 librealsense 测试（无 ROS）A-E 全失败 → 排除 ROS/软件
3. profile 枚举完整 → 排除 EEPROM 静态表缺失
4. option 探测：仅 Depth Units 失败 → 校准读取链路异常
5. 内核：UVC XU control -32 (EPIPE) → vendor 控制通道异常
6. 固件 hardware_reset() 无效 → 非固件运行状态
7. 源码定位：0x2C = GET_ADV；参数 9 = DS5_ASIC_AND_PROJECTOR_TEMPERATURES
  ↓
诊断：module EEPROM/校准读取链路异常（硬件层）
  ↓
用户检查：排线（interposer）脱落 → 重新插好 → 全部恢复 ✅
```

## 4. 验证命令

```bash
# 完整诊断（只读）
bash ~/vio-improve/scripts/diagnose_realsense_hwmon.sh

# 确认 USB3
lsusb -t | grep -A2 uvcvideo        # 期望 5000M / SuperSpeed
cat /sys/bus/usb/devices/2-1/speed  # 期望 5000

# 裸测 848x480@30（USB3 下）
cd ~/vio-improve/scripts && LD_LIBRARY_PATH=/opt/ros/humble/lib/aarch64-linux-gnu ./test848
```

## 5. 下一步（Stage 1B）

1. 用户将相机换插 USB3 口（Bus 02）→ `cat /sys/bus/usb/devices/2-1/speed` = 5000
2. 重启 vio.service → camera.log 应出现 `Open profile: Infra(1/2) 848x480@30`
3. `ros2 topic hz` 验证 infra1/2 ≈30Hz
4. 生成 docs/D430_848x480_30_BASELINE.md → Stage 1.5 VIO baseline

## 6. 禁止事项

- ❌ 不刷 firmware（当前 5.17.3.10 功能正常）
- ❌ 不写 EEPROM / 覆盖 calibration
- ❌ 不执行破坏性操作
