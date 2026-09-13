#!/bin/bash
# Start foxglove_bridge and system_monitor in background
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=42
export ROS_LOCALHOST_ONLY=1

# Start foxglove_bridge
ros2 run foxglove_bridge foxglove_bridge --ros-args -p port:=8765 -p address:=0.0.0.0 > /tmp/foxglove.log 2>&1 &
FOXLOVE_PID=$!
echo "foxglove_bridge PID: $FOXLOVE_PID"

# Start system_monitor
python3 /home/orangepi/vio-improve/scripts/system_monitor.py > /tmp/system_monitor.log 2>&1 &
MONITOR_PID=$!
echo "system_monitor PID: $MONITOR_PID"

sleep 5
echo "=== foxglove log ==="
tail -5 /tmp/foxglove.log
echo "=== monitor log ==="
tail -3 /tmp/system_monitor.log
echo "=== system topics ==="
ros2 topic list 2>/dev/null | grep -E 'system|cpu|mem'
echo "=== foxglove channel count ==="
grep -c 'Advertising new channel' /tmp/foxglove.log
