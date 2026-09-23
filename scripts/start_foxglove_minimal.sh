#!/usr/bin/env bash
# Start a low-bandwidth Foxglove bridge for observing VIO pose and path.
set -eu

WS="${VIO_WS:-$HOME/kswlt/vio_ws}"
LOG_DIR="${VIO_LOG_DIR:-/tmp/vio}"
PID_FILE="$LOG_DIR/foxglove.pid"
LOG_FILE="$LOG_DIR/foxglove_manual.log"
mkdir -p "$LOG_DIR"

if ss -ltn 2>/dev/null | grep -q ':8765 '; then
  echo "Foxglove bridge is already listening on port 8765."
  exit 0
fi

nohup bash -c '
  source /opt/ros/humble/setup.bash
  source "$1/install/setup.bash"
  export ROS_DOMAIN_ID=42 ROS_LOCALHOST_ONLY=1
  exec ros2 run foxglove_bridge foxglove_bridge --ros-args \
    -p address:=0.0.0.0 -p port:=8765 \
    -p "topic_whitelist:=['/poseimu','/tf_static']"
' _ "$WS" >"$LOG_FILE" 2>&1 </dev/null &
echo $! > "$PID_FILE"

for _ in $(seq 1 10); do
  if ss -ltn 2>/dev/null | grep -q ':8765 '; then
    echo "Foxglove bridge listening on 0.0.0.0:8765"
    echo "Topics whitelisted: /poseimu (about 15 Hz), /tf_static"
    echo "Log: $LOG_FILE"
    exit 0
  fi
  sleep 1
done
echo "Foxglove bridge failed to open port 8765; see $LOG_FILE" >&2
tail -30 "$LOG_FILE" >&2 || true
exit 1
