#!/bin/bash
echo "=== SYSTEMD SERVICES (realsense/ros) ==="
systemctl list-units --type=service --all 2>/dev/null | grep -iE 'realsense|ros|camera' || echo "none found"
systemctl list-unit-files 2>/dev/null | grep -iE 'realsense|ros|camera' || echo "no unit files"

echo "=== CRON ==="
crontab -l 2>/dev/null || echo "no crontab"
cat /etc/crontab 2>/dev/null | grep -iE 'realsense|ros|camera' || echo "no cron entries"

echo "=== RC.LOCAL / INIT ==="
cat /etc/rc.local 2>/dev/null || echo "no rc.local"
ls /etc/init.d/ 2>/dev/null | grep -iE 'realsense|ros|camera' || echo "no init.d"

echo "=== PROCESSES TREE around realsense ==="
ps -ef | grep -iE 'realsense|ros2|launch' | grep -v grep

echo "=== WHO STARTED IT (parent process) ==="
PPID_ROS=$(ps -o ppid= -p 623574 2>/dev/null | tr -d ' ')
echo "Parent PID of ros2 launch: $PPID_ROS"
if [ -n "$PPID_ROS" ] && [ "$PPID_ROS" != "1" ]; then
    ps -fp "$PPID_ROS" 2>/dev/null
fi

echo "=== USER AUTOSTART ==="
ls -la ~/.config/autostart/ 2>/dev/null || echo "no autostart dir"
cat ~/.bashrc 2>/dev/null | grep -iE 'realsense|ros2 launch' || echo "no bashrc launch"
cat ~/.profile 2>/dev/null | grep -iE 'realsense|ros2 launch' || echo "no profile launch"
