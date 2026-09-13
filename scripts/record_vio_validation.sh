#!/usr/bin/env bash
# Usage: record_vio_validation.sh STATIC 120 [operator notes]
set -euo pipefail
source /opt/ros/humble/setup.bash
source /home/orangepi/vio_ws/install/setup.bash
export ROS_DOMAIN_ID=42 ROS_LOCALHOST_ONLY=1
exec python3 "$(dirname "$0")/record_vio_validation.py" "$@"
