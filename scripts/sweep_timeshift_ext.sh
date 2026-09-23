#!/bin/bash
# sweep_timeshift_ext.sh -- extend the timeshift sweep past -0.015 to find the minimum.
# The first sweep was monotone decreasing over 0 -> -0.015 with no sign of a floor,
# so the optimum is at least -0.015; this probes further negative.
W=/home/orangepi/kswlt/vio_replay
BAG=/home/orangepi/vio_data/20260922T235522Z_LASEROFF3/bag
BASE=$W/configs/base
DOM=43

run () {
  local name=$1 ; local ts=$2
  echo "=================================================================="
  echo "### EXT $name  timeshift=$ts   $(date -Is)"
  echo "=================================================================="
  python3 $W/mksweep.py "$BASE" "$W/configs/$name" "timeshift_cam_imu=$ts" || return 1
  rm -rf "$W/out/$name"
  bash $W/replay_one.sh "$BAG" "$W/configs/$name" "$W/out/$name" "$name" $DOM
  echo "### EXT $name done"
}

run ext_m18 -0.018
run ext_m20 -0.020
run ext_m24 -0.024
run ext_m30 -0.030

echo "=================================================================="
echo "### EXT COMPLETE $(date -Is)"
echo "=================================================================="
