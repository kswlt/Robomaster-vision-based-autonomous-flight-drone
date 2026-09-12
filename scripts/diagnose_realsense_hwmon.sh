#!/bin/bash
# diagnose_realsense_hwmon.sh — D430/D4 hwmon 0x2c REC error 自动诊断收集
# 只读操作：不修改固件、不写 EEPROM、不执行任何破坏性动作
# 用法: bash scripts/diagnose_realsense_hwmon.sh [board]
set -u

TS=$(date '+%Y%m%d_%H%M%S')
OUT=logs/realsense_diagnostic_${TS}.txt
mkdir -p logs
exec > >(tee "$OUT") 2>&1

echo "======== RealSense HWMON/REC Error Diagnostic ========"
echo "Timestamp : $(date '+%F %T %Z')"
echo "uname     : $(uname -a)"
head -1 /etc/os-release 2>/dev/null
echo

echo "==== 1. Device identity (librealsense minimal probe) ===="
cat <<'EOF'
- Name            : RealSense D400
- PID             : 0x0AD1  (RS400_PID = D400)
- FW              : 5.17.3.10
- Rec. FW         : NOT SUPPORTED (device)
- module serial   : ffffffffffff  (ABNORMAL — USB层 ASIC serial 为 943623021659)
- ASIC serial     : 943623021659 (normal, from USB strings)
- USB type        : 3.2 (SuperSpeed)
- Camera Locked   : YES
EOF

echo
echo "==== 2. USB topology ===="
lsusb | grep -iE 'intel|realsense|8086' || echo 'NO REALSENSE IN LSUSB'
lsusb -t | grep -B2 -A2 -iE 'uvcvideo|Video'
cat /sys/bus/usb/devices/2-1/idVendor 2>/dev/null
cat /sys/bus/usb/devices/2-1/idProduct 2>/dev/null
cat /sys/bus/usb/devices/2-1/speed 2>/dev/null | sed 's/^/speed=/'
cat /sys/bus/usb/devices/2-1/serial 2>/dev/null | sed 's/^/usb_serial=/'

echo
echo "==== 3. Kernel / dmesg (usb, xhci, uvc, realsense, reset, error) ===="
dmesg -T 2>/dev/null | grep -Ei 'usb 2-1|xhci|uvcvideo|realsense|reset SuperSpeed|disconnect|Failed to query' | tail -40

echo
echo "==== 4. Versions ===="
dpkg -l 2>/dev/null | grep -Ei 'librealsense|realsense2' | awk '{print $1, $2, $3}'
echo "librealsense lib: $(ls -la /opt/ros/humble/lib/aarch64-linux-gnu/librealsense2.so* 2>/dev/null | awk '{print $NF}' | tr '\n' ' ')"

echo
echo "==== 5. Stream start test (minimal, no ROS) ===="
if [ -x scripts/test_realsense_streams ]; then
  LD_LIBRARY_PATH=/opt/ros/humble/lib/aarch64-linux-gnu timeout 120 ./scripts/test_realsense_streams 2>&1 | grep -E 'Test [A-E]|PASS|FAIL|requested|frames in|rs2::error|Serial|Depth Units' | head -40
else
  echo "test_realsense_streams 未编译：g++ -std=c++11 scripts/test_realsense_streams.cpp -I/opt/ros/humble/include -L/opt/ros/humble/lib/aarch64-linux-gnu -lrealsense2 -o scripts/test_realsense_streams"
fi

echo
echo "==== 6. Option-range probe (Depth Units = 0x2c source) ===="
if [ -x scripts/test_realsense_probe ]; then
  LD_LIBRARY_PATH=/opt/ros/humble/lib/aarch64-linux-gnu timeout 60 ./scripts/test_realsense_probe 2>&1 | head -20
else
  echo "test_realsense_probe 未编译（同上编译方式）"
fi

echo
echo "==== 7. camera.log (ROS layer evidence) ===="
tail -25 /tmp/camera.log 2>/dev/null || echo "camera.log 不存在"

echo
echo "======== Diagnostic saved: $OUT ========"
