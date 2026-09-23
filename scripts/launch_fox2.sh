#!/bin/bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=1
source /opt/ros/humble/setup.bash
# start trajectory node
pkill -9 -f odom_to_path.py 2>/dev/null
sleep 1
nohup python3 /tmp/odom_to_path.py > /tmp/odom_to_path.log 2>&1 &
sleep 2
# restart foxglove bridge without 579Hz /tf, without /poseimu, without images
pkill -9 -f foxglove_bridge 2>/dev/null
sleep 2
nohup ros2 run foxglove_bridge foxglove_bridge --ros-args -p topic_filter:='[/odomimu,/trajectory,/tf_static]' > /tmp/foxglove.log 2>&1 &
sleep 6
echo READY
