#!/bin/bash
# Camera diagnostic script for Orange Pi 5
echo "=== V4L2 DEVICE INFO ==="
for dev in /dev/video0 /dev/video1 /dev/video2 /dev/video3; do
    echo "--- $dev ---"
    v4l2-ctl -d "$dev" --info 2>&1 | head -15
    echo
done

echo "=== V4L2 FORMATS video0 ==="
v4l2-ctl -d /dev/video0 --list-formats-ext 2>&1 | head -50

echo "=== V4L2 FORMATS video2 ==="
v4l2-ctl -d /dev/video2 --list-formats-ext 2>&1 | head -30

echo "=== ROS2 REALSENSE NODE ==="
ps aux | grep -i realsense | grep -v grep || echo "none"

echo "=== WEB_VIS LOG (last 50) ==="
tail -50 ~/kswlt_e2d/web_vis.log 2>/dev/null || echo "no log"

echo "=== USB DETAILS D430 ==="
lsusb -v -d 8086:0ad4 2>&1 | head -60

echo "=== UDEV RULES ==="
ls -la /etc/udev/rules.d/ 2>&1 | grep -i realsense
cat /etc/udev/rules.d/*realsense* 2>/dev/null || echo "no realsense udev rules"
