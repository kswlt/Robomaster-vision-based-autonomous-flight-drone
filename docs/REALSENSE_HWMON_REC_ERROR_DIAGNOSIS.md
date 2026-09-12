# REALSENSE HWMON / REC ERROR DIAGNOSIS — D430/D4 链路故障

> 状态：**Stage 1A 诊断完成（CASE A 确认）**，问题定位在设备/固件/module/board 硬件层
> 日期：2026-09-13
> 设备：RealSense D400（PID 0x0AD1）@ OrangePi5 (RK3588)

---

## 1. 当前已确认事实（实测证据）

### 1.1 设备枚举正常（USB 层）
- `lsusb`：`8086:0ad1` Intel RealSense Depth Camera 400
- USB 拓扑：Bus 02 (xhci, SuperSpeed 5000M) Port 1，uvcvideo 绑定 3 个 Video 接口
- `/sys/bus/usb/devices/2-1/speed` = **5000**（SuperSpeed）
- dmesg USB 字符串：SerialNumber = **943623021659**（ASIC 串号正常）
- FW：5.17.3.10，bcdDevice 51.13

### 1.2 librealsense 层身份字段（异常项标 ⚠️）
| 字段 | 值 | 判定 |
|---|---|---|
| Name | RealSense D400 | 正常 |
| Product Id | 0AD1 = **RS400_PID（D400）** | ⚠️ 非 D430-with-tracking(0x0ad5) |
| Firmware Version | 5.17.3.10 | 正常读取 |
| **Recommended FW** | **not supported by the device!** | ⚠️ 异常 |
| **Serial Number** | **ffffffffffff** | ⚠️ 异常（USB 层为 943623021659） |
| ASIC Serial | 943623021659 | 正常 |
| FW Update Id | 943623021659 | 正常 |
| USB Type | 3.2 | 正常 |
| Camera Locked | YES | 正常 |
| Advanced Mode | YES | 正常 |
| Product Line | D400 | 正常 |

### 1.3 流启动测试（最小 librealsense，绕过 ROS）— **全部失败**
用 C++ 最小程序直接链接 librealsense 2.58.3（无 ROS/OpenVINS）：
- Test A infra1 only → `hwmon command 0x2c( 9 0 0 0 ) failed (response -9= No expected user action)`
- Test B infra2 only → 同
- Test C infra1+infra2 → 同
- Test D depth only → 同
- Test E IR1+IR2+depth → 同
- 使用最保守 profile（424x240@6）仍失败

### 1.4 Profile 枚举 — **完整正常**
Stereo Module 枚举出全部标准 profile：
- Infrared idx=1: Y8 640x480@30/60/90, 848x480@30/60/90, ...
- Infrared idx=2: Y8 848x480@30 等（含 848x480@30）
- Depth: Z16 848x480@30/60/90, 640x480@30, ...
- **profile 表完整 → EEPROM/校准静态表大概率正常**

### 1.5 hwmon 0x2c 调用来源定位（源码级）
librealsense `ds::fw_cmd` 枚举：**`GET_ADV = 0x2C`**（Get Advanced Mode 参数）。
- 触发场景：`rs2_get_option_range(option=28 /*RS2_OPTION_DEPTH_UNITS*/)` → `hwmon command 0x2c(9 1 0 0)` → 设备无响应（-9）
- option 探测结果：**仅 Depth Units(28) 失败**；VISUAL_PRESET/EXPOSURE/GAIN/AUTO_EXPOSURE 等全部正常
- Depth Units 存储在 module 校准数据/EEPROM 中 → **读取链路异常**
- 设备无响应错误码 -9 = librealsense "No expected user action" = 固件未按预期响应命令

### 1.6 内核级证据
- `usb 2-1: Failed to query (GET_CUR) UVC control 11 on unit 3: -32 (exp. 1)` —— **UVC 扩展单元(XU)控制传输失败（-EPIPE）**，librealsense hwmon 正走 XU 通道

### 1.7 已尝试的恢复手段（均无效）
| 手段 | 结果 |
|---|---|
| ROS launch 参数修复（infra_profile） | 无效（设备层错误） |
| vio.service 重启 ×2 | 无效 |
| USB authorized 重新枚举 | 无效（SuperSpeed 正常重枚举） |
| **固件 hardware_reset()（无破坏）** | 无效（serial 仍 ffffff，Depth Units 仍 FAIL） |

---

## 2. 尚未确认事实
- 是否供电不足（需现场检查供电/换口/换线验证）
- module↔board（interposer/排线）接触是否良好（需现场物理检查）
- EEPROM 芯片是否物理损坏（需尝试只读备份验证或换模组验证）
- firmware 与 module/board 组合是否匹配（当前 5.17.3.10）
- 该模组实际硬件型号丝印（D400 vs D430 模组，需现场看丝印）

## 3. 已排除项
- ❌ ROS2 / realsense2_camera wrapper 层（最小 librealsense 同样失败）
- ❌ OpenVINS / navigation code（未参与）
- ❌ 848×480@30 带宽不足（424x240@6 也失败；USB SuperSpeed）
- ❌ launch 参数（已修复为 depth_module.infra_profile，非根因）
- ❌ USB 枚举/链路断（SuperSpeed 正常、串号在 USB 层正常）
- ❌ 固件运行状态卡死（hardware_reset 无效）
- ❌ profile/EEPROM 静态表缺失（profile 完整）

## 4. 当前怀疑项（按概率排序）
1. **module ↔ board（interposer/排线）通信异常** —— EEPROM/校准读取失败 + 固件命令无响应（XU 传输 -32）均指向内部通信链路
2. **module EEPROM 数据异常/损坏** —— module serial 读不出（ffffffffffff）、Recommended FW 读不出
3. **供电不足/电源质量问题** —— 能枚举但启动/读取内部资源失败
4. **firmware 与 module 组合版本异常** —— 需对照 recommended firmware
5. **module 硬件损坏**（ASIC/EEPROM 物理故障）

## 5. 验证命令（现场执行）
```bash
# 5.1 完整诊断收集（只读）
bash ~/vio-improve/scripts/diagnose_realsense_hwmon.sh

# 5.2 手动复查（电源/换线后）
lsusb -t | grep -A2 uvcvideo
cat /sys/bus/usb/devices/2-1/speed    # 期望 5000
# 若 Depth Units 恢复可读，说明供电/链路改善
```

## 6. 下一步决策树
```
电源/线/口/连接 处理后
  ├─ Depth Units 恢复可读 + 流可启动
  │     └─ Stage 1A PASS → Stage 1B 848x480@30
  ├─ 仍失败，但换另一台 D4xx 模组可启动
  │     └─ 原模组 EEPROM/硬件损坏，需更换模组
  └─ 仍失败，且所有模组都失败
        └─ 板端 USB/供电问题，检查 board 侧
```

## 7. 需要用户现场执行的物理操作（无破坏性）
1. **彻底断电**：拔相机 USB 线 ≥30 秒（让 module 完全放电），重新插回同一口 → 复查
2. **换 USB 线**（短、高质量 USB3 认证线）→ 复查
3. **换 USB 口**（板子其他 USB3 口）→ 复查
4. **检查供电**：确认 board 供电充足（建议外接带电源 USB hub 测试）→ 复查
5. **检查连接**：确认 module 与 board 的 interposer/排线连接牢固、无氧化（若可触及）
6. **记录丝印**：module 与 board 上丝印型号（判断 D400/D430 实际模组）

每次操作后执行：`bash ~/vio-improve/scripts/diagnose_realsense_hwmon.sh`，把输出发回。

## 8. 禁止事项（用户规则）
- ❌ 不刷 firmware（除非确认版本不匹配后另行授权）
- ❌ 不写 EEPROM / 覆盖 calibration / factory reset
- ❌ 不执行任何高级模式写操作

---

*诊断结论：问题位于 RealSense 设备/固件/module/board 层（CASE A）。软件层已穷尽，等待硬件层现场操作验证。*
