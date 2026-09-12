#!/bin/bash
# check_camera_profile.sh — D430 相机状态一键诊断
# 显示: requested IR profile / actual IR profile / actual FPS / USB speed / REC error / depth profile
# 用法: bash scripts/check_camera_profile.sh   (板端执行)
set -u
source /opt/ros/humble/setup.bash 2>/dev/null
export ROS_DOMAIN_ID=42 ROS_LOCALHOST_ONLY=1

echo "======== D430 Camera Profile Check $(date '+%F %T') ========"

echo
echo "--- 1. USB 设备 (lsusb) ---"
lsusb | grep -iE 'intel|realsense|8086' || echo 'NO REALSENSE DEVICE FOUND'

echo
echo "--- 2. USB 拓扑/速度 (lsusb -t) ---"
lsusb -t 2>/dev/null | grep -B1 -A1 -iE 'uvcvideo|Video' || lsusb -t 2>/dev/null

echo
echo "--- 3. 请求的 IR profile (start_vio_systemd.sh) ---"
grep -oE 'depth_module.infra_profile:[^ ]*|infra_(fps|width|height):=[0-9]+' /home/orangepi/start_vio_systemd.sh 2>/dev/null || echo 'NO PROFILE PARAM FOUND IN START SCRIPT'
grep -oE 'enable_depth:[a-z]+|enable_infra[12]:[a-z]+' /home/orangepi/start_vio_systemd.sh 2>/dev/null

echo
echo "--- 4. 实际输出 (camera.log) ---"
if [ -f /tmp/camera.log ]; then
  echo "[最近 Open profile 相关]"
  grep -iE 'Open profile|Width|Height|FPS|profile' /tmp/camera.log | tail -6
  echo "[REC/错误]"
  grep -iE 'REC|hwmon|Error starting|disconnect|failed|error' /tmp/camera.log | tail -6
else
  echo 'camera.log 不存在'
fi

echo
echo "--- 5. 实际话题与频率 (ROS2) ---"
for t in /camera/camera/infra1/image_rect_raw /camera/camera/infra2/image_rect_raw; do
  echo "--- $t ---"
  timeout 5 ros2 topic info "$t" 2>&1 | grep -E 'Type|Publisher|Subscription'
  timeout 6 ros2 topic hz "$t" 2>&1 | tail -2
done

echo
echo "--- 6. 相机节点进程 ---"
ps aux | grep -E 'realsense2_camera_node' | grep -v grep | head -2

echo
echo "======== DONE ========"
