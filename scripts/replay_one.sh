#!/bin/bash
# replay_one.sh -- deterministic offline OpenVINS replay of one raw bag.
# usage: replay_one.sh <rawbag_dir> <config_dir> <out_dir> <label> [domain]
# NOTE: no `set -u` -- ROS setup.bash dereferences unset vars.
set -o pipefail
RAW=$1; CFG=$2; OUT=$3; LABEL=$4; DOM=${5:-43}
mkdir -p "$OUT"

source /opt/ros/humble/setup.bash
source /home/orangepi/kswlt/vio_ws/install/setup.bash
export ROS_DOMAIN_ID=$DOM
export ROS_LOCALHOST_ONLY=1
export RCUTILS_COLORIZED_OUTPUT=0

echo "############ REPLAY $LABEL ############"
echo "  bag    = $RAW"
echo "  config = $CFG"
echo "  domain = $DOM"
echo "  started= $(date -Is)"
sha256sum "$CFG"/estimator_config.yaml "$CFG"/kalibr_imu_chain.yaml "$CFG"/kalibr_imucam_chain.yaml 2>/dev/null | sed 's/^/  cfg /'
echo "  timeshift: $(grep timeshift_cam_imu "$CFG"/kalibr_imucam_chain.yaml)"

pkill -KILL -f 'run_subscribe_msckf' 2>/dev/null
pkill -KILL -f 'ros2 bag play' 2>/dev/null
pkill -KILL -f 'ros2 bag record' 2>/dev/null
sleep 2

echo "  --- starting estimator ---"
"$HOME/kswlt/vio_ws/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf" \
  --ros-args -p config_path:="$CFG/estimator_config.yaml" -p publish_tf:=false \
  > "$OUT/ov.log" 2>&1 &
OVPID=$!
sleep 6
if ! kill -0 $OVPID 2>/dev/null; then
  echo "  !! estimator died on startup"; cat "$OUT/ov.log" | head -30; exit 1
fi
echo "  ov pid=$OVPID alive"

echo "  --- starting recorder ---"
ros2 bag record -o "$OUT/odom" /odomimu /imu > "$OUT/record.log" 2>&1 &
RECPID=$!
sleep 5
if ! kill -0 $RECPID 2>/dev/null; then
  echo "  !! recorder died"; cat "$OUT/record.log" | head -30
fi

echo "  --- playing bag (wall clock) ---"
PLAY_T0=$(date +%s.%N)
ros2 bag play "$RAW" --rate 1.0 > "$OUT/play.log" 2>&1
PLAY_RC=$?
PLAY_T1=$(date +%s.%N)
echo "  bag play rc=$PLAY_RC wall=$(awk "BEGIN{printf \"%.1f\", $PLAY_T1-$PLAY_T0}") s"

echo "  --- draining estimator queue (25 s) ---"
sleep 25

kill -INT $RECPID 2>/dev/null; sleep 4
kill -TERM $RECPID 2>/dev/null; sleep 2
kill -KILL $RECPID 2>/dev/null
kill -INT $OVPID 2>/dev/null; sleep 4
kill -KILL $OVPID 2>/dev/null
sleep 2

echo "  --- results ---"
echo "  ov.log lines = $(wc -l < "$OUT/ov.log" 2>/dev/null || echo 0)"
echo "  LOADED lines:"
grep -a '^LOADED' "$OUT/ov.log" 2>/dev/null | sed 's/^/    /'
echo "  init:"
grep -a -A6 'successful initialization' "$OUT/ov.log" 2>/dev/null | head -12 | sed 's/^/    /'
echo "  init warnings: $(grep -a -c 'unable to select window' "$OUT/ov.log" 2>/dev/null || echo 0) x unable-to-select-window"
echo "  zupt passed=$(grep -a -c 'passed disparity' "$OUT/ov.log" 2>/dev/null || echo 0) accepted=$(grep -a -c 'ZUPT\]: accepted' "$OUT/ov.log" 2>/dev/null || echo 0)"
echo "  final state:"
grep -a -E '^(q_GtoI|bg =)' "$OUT/ov.log" 2>/dev/null | tail -2 | sed 's/^/    /'
echo "  odom bag:"; ls -la "$OUT/odom" 2>/dev/null | sed 's/^/    /'
echo "  ended= $(date -Is)"
echo "############ DONE $LABEL ############"
