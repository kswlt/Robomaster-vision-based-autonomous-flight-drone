#!/bin/bash
cd /home/orangepi/kswlt/vio_ws
source /opt/ros/humble/setup.bash
export MAKEFLAGS="-j2"
colcon build --parallel-workers 2 --cmake-args -DCMAKE_BUILD_TYPE=Release --packages-select ov_msckf
echo "BUILD_DONE"
