#!/bin/bash
# VIO系统启动脚本（供systemd调用）
# 设计：flock防止多实例 + 前台跟随VIO生命周期（VIO退出→脚本退出→systemd重启）

# 加锁防止多实例堆积
exec 9>/tmp/vio_restart.lock
flock -n 9 || { echo "[$(date)] 已有VIO实例在运行，退出" >> /tmp/vio_restart.log; exit 0; }

# 等待USB设备就绪
sleep 3

# 设置ROS环境
source /opt/ros/humble/setup.bash
source /home/orangepi/vio_ws/install/setup.bash
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=42

# 清理旧进程（脚本自身命令行不含这些字符串，安全）
pkill -9 -f 'install/ov_msckf' 2>/dev/null
pkill -9 -f 'vio_bridge_combined' 2>/dev/null
pkill -9 -f 'realsense2_camera' 2>/dev/null
sleep 2

# 自动检测飞控串口
SERIAL_PORT=$(ls /dev/ttyACM* 2>/dev/null | head -1)
if [ -z "$SERIAL_PORT" ]; then
    SERIAL_PORT="/dev/ttyACM0"
fi
echo "飞控串口: $SERIAL_PORT" > /tmp/vio_serial.log

echo "[$(date)] VIO系统启动，串口=$SERIAL_PORT" >> /tmp/vio_restart.log

# 启动D430相机
nohup ros2 launch realsense2_camera rs_launch.py \
    enable_infra1:=true enable_infra2:=true \
    enable_color:=false enable_depth:=false \
    infra_fps:=30 infra_width:=848 infra_height:=480 \
    > /tmp/camera.log 2>&1 &

sleep 6

# 启动合并桥接节点（自动检测串口）
nohup python3 /home/orangepi/vio_ws/vio_bridge/vio_bridge_combined.py \
    --ros-args -p serial_port:=$SERIAL_PORT \
    > /tmp/vio_bridge.log 2>&1 &

sleep 4

# 启动OpenVINS（前台，跟随其生命周期）
ros2 run ov_msckf run_subscribe_msckf \
    --ros-args -p config_path:=/home/orangepi/vio_ws/src/open_vins/config/d430/estimator_config.yaml \
    >> /tmp/vio.log 2>&1

# VIO退出，记录并退出（systemd会重启整个服务）
VIO_EXIT=$?
echo "[$(date)] OpenVINS退出，退出码: $VIO_EXIT，等待systemd重启..." >> /tmp/vio_restart.log
exit $VIO_EXIT
