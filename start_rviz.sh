#!/bin/bash
# 启动RViz可视化

source /opt/ros/humble/setup.bash
source ~/vio_ws/install/setup.bash
export ROS_LOCALHOST_ONLY=1
export ROS_DOMAIN_ID=42

# 使用OpenVINS自带的rviz配置
rviz2 -d ~/vio_ws/vio_bridge/config/vio_display.rviz
