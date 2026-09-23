#!/usr/bin/env bash
# Run as a dedicated systemd unit with KillMode=control-group. Preserves flight latch.
set -eo pipefail
source /opt/ros/humble/setup.bash
source /home/orangepi/vio_ws/install/setup.bash
export ROS_DOMAIN_ID="${VIO_CAPTURE_DOMAIN:-42}"
if [ "${VIO_CAPTURE_TRANSPORT:-udp}" = shm ]; then
  export ROS_LOCALHOST_ONLY=1
  unset FASTRTPS_DEFAULT_PROFILES_FILE
else
  export ROS_LOCALHOST_ONLY=0
  export FASTRTPS_DEFAULT_PROFILES_FILE=/home/orangepi/fastdds_udp_diagnostic.xml
fi
exec 9>/tmp/vio_restart.lock
flock -n 9 || { echo 'Another VIO stack owns capture devices'; exit 1; }
if systemctl is-active --quiet vio.service; then
  echo 'Stop production VIO before diagnostic capture'; exit 1
fi
SCRIPT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
SESSION_DIR=/home/orangepi/vio_data/capture_$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$SESSION_DIR"
export VIO_IMU_TRACE="$SESSION_DIR/imu_time_mapping.csv"
echo "CAPTURE_SESSION=$SESSION_DIR"
ros2 launch realsense2_camera rs_launch.py enable_infra1:=true enable_infra2:=true \
  enable_color:=false enable_depth:=false depth_module.infra_profile:=848x480x30 \
  > "$SESSION_DIR/camera.log" 2>&1 &
python3 -u "$SCRIPT_DIR/trace_vio_imu.py" --ros-args \
  -p serial_port:=/dev/ttyACM0 -p send_vision_to_px4:=false \
  -p odom_topic:=/validation/no_flight_odometry > "$SESSION_DIR/bridge.log" 2>&1 &
sleep 12
# Output is recorded but cannot reach the bridge's unrelated odometry topic.
ros2 run ov_msckf run_subscribe_msckf --ros-args \
  -p config_path:=/home/orangepi/vio_ws/src/open_vins/config/d430/estimator_config.yaml \
  > "$SESSION_DIR/estimator.log" 2>&1 &
python3 "$SCRIPT_DIR/record_vio_validation.py" "$@"
