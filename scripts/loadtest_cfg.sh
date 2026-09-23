#!/bin/bash
# loadtest_cfg.sh -- does OpenVINS actually accept this config?
#
# The definitive test for a kalibr-style chain: hand it to the real binary and
# read the LOADED_* lines it prints.  OpenCV 5.x's Python FileStorage API is not
# a reliable validator for these files (the long-standing '%YAML:1.0' dialect
# plus plain YAML sequences for the 4x4 matrices), so we do not rely on it.
#
# Usage: loadtest_cfg.sh <config_dir> [seconds]
set -o pipefail

CFG=$1
SECS=${2:-8}
WS=/home/orangepi/kswlt/vio_ws
DOM=${ROS_DOMAIN_ID:-44}          # separate domain: does not disturb other work
OUT=/tmp/loadtest_$(date +%s).log

source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
export ROS_DOMAIN_ID=$DOM
export ROS_LOCALHOST_ONLY=1
export RCUTILS_COLORIZED_OUTPUT=0

echo "=== load test: $CFG/estimator_config.yaml (domain $DOM, ${SECS}s) ==="
grep -h -E 'timeshift_cam_imu' "$CFG/kalibr_imucam_chain.yaml" | head -1 | sed 's/^/  file says: /'

"$WS/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf" \
    --ros-args -p config_path:="$CFG/estimator_config.yaml" -p publish_tf:=false \
    > "$OUT" 2>&1 &
PID=$!

sleep "$SECS"
kill -INT $PID 2>/dev/null
sleep 2
kill -KILL $PID 2>/dev/null

echo "  --- LOADED_* lines ---"
grep -a -E '^LOADED_' "$OUT" | sed 's/^/  /'
echo "  --- subscribe lines ---"
grep -a 'subscribing' "$OUT" | sed 's/^/  /'
echo "  --- errors / fatal ---"
if grep -a -qiE 'error|fatal|terminate|what\(\)|failed to' "$OUT"; then
  grep -a -iE 'error|fatal|terminate|what\(\)|failed to' "$OUT" | head -10 | sed 's/^/  /'
  RC=1
else
  echo "  (none)"
  RC=0
fi

TS=$(grep -a '^LOADED_CAMERA_IMU_TIME_OFFSET_SEC' "$OUT" | head -1 | cut -d= -f2)
echo "  --- verdict ---"
if [ -n "$TS" ]; then
  echo "  loaded timeshift = $TS"
  if [ "$(printf '%.6f' "$TS")" = "-0.015000" ]; then
    echo "  LOADTEST PASS: OpenVINS accepted the config and loaded -0.015"
  else
    echo "  LOADTEST NOTE: loaded $TS (check the intended value)"
  fi
else
  echo "  LOADTEST FAIL: no LOADED_CAMERA_IMU_TIME_OFFSET_SEC -- config did not load"
  RC=1
fi
echo "  raw log: $OUT"
exit $RC
