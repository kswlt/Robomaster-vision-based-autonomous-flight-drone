#!/bin/bash
# ============================================
# VIO一键启动脚本
# 硬件：香橙派Pi5 + D430相机 + PX4飞控
# 算法：OpenVINS (MSCKF)
# ============================================

echo "========================================"
echo "  VIO系统启动中..."
echo "  香橙派Pi5 + D430 + PX4 + OpenVINS"
echo "========================================"

# 清理旧进程
echo "[1/4] 清理旧进程..."
pkill -f run_subscribe_msckf 2>/dev/null
pkill -f realsense2_camera 2>/dev/null
pkill -f vio_bridge_combined 2>/dev/null
sleep 2

# 设置ROS环境
source /opt/ros/humble/setup.bash
source ~/vio_ws/install/setup.bash
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=42

# 启动D430相机
echo "[2/4] 启动D430双目相机..."
nohup ros2 launch realsense2_camera rs_launch.py \
    enable_infra1:=true enable_infra2:=true \
    enable_color:=false enable_depth:=false \
    depth_module.infra_profile:=848x480x30 \
    > /tmp/camera.log 2>&1 &
sleep 6

# 启动合并桥接节点（IMU读取 + VIO数据回传）
echo "[3/4] 启动PX4桥接节点..."
nohup python3 ~/vio_ws/vio_bridge/vio_bridge_combined.py > /tmp/vio_bridge.log 2>&1 &
sleep 4

# 启动OpenVINS
echo "[4/4] 启动OpenVINS..."
nohup ros2 run ov_msckf run_subscribe_msckf \
    --ros-args -p config_path:=/home/orangepi/vio_ws/src/open_vins/config/d430/estimator_config.yaml \
    > /tmp/vio.log 2>&1 &
sleep 5

echo ""
echo "========================================"
echo "  VIO系统启动完成!"
echo "========================================"
echo ""
echo "节点状态:"
ros2 node list 2>/dev/null
echo ""
echo "数据频率:"
echo -n "  IMU:    "; timeout 2 ros2 topic hz /imu 2>/dev/null | grep "average" | awk '{print $3" Hz"}'
echo -n "  左相机: "; timeout 2 ros2 topic hz /camera/camera/infra1/image_rect_raw 2>/dev/null | grep "average" | awk '{print $3" Hz"}'
echo -n "  VIO里程计: "; timeout 2 ros2 topic hz /odomimu 2>/dev/null | grep "average" | awk '{print $3" Hz"}'
echo ""
echo "常用命令:"
echo "  查看里程计: ros2 topic echo /odomimu --once"
echo "  查看VIO日志: tail -f /tmp/vio.log"
echo "  查看桥接日志: tail -f /tmp/vio_bridge.log"
echo "  停止系统: pkill -f 'run_subscribe|realsense|vio_bridge'"
echo ""
echo "注意: 首次启动请轻轻晃动相机10秒完成初始化"
