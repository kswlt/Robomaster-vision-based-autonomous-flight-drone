#!/bin/bash
# sweep_timeshift.sh -- single-variable A/B of timeshift_cam_imu on ONE immutable bag
# Every run uses identical code/config except timeshift (one variable at a time).
W=/home/orangepi/kswlt/vio_replay
BAG=/home/orangepi/vio_data/20260922T235522Z_LASEROFF3/bag
DOM=43
mkdir -p $W/logs $W/out

run () {
  local name=$1 ; local ts=$2
  echo "=================================================================="
  echo "### SWEEP $name  timeshift=$ts   $(date -Is)"
  echo "=================================================================="
  if [ "$ts" = "KEEP" ]; then
    rm -rf $W/configs/$name
    cp -a $W/configs/base $W/configs/$name
  else
    bash $W/mkcfg.sh $name "$ts" >/dev/null 2>&1
  fi
  rm -rf $W/out/$name
  bash $W/replay_one.sh "$BAG" "$W/configs/$name" "$W/out/$name" "$name" $DOM
  echo "### SWEEP $name done, odom bag:"
  ls -la "$W/out/$name/odom" 2>/dev/null | tail -3
}

# --- timeshift sweep (order matters: run the reference value FIRST) ---
run ts_m10   -0.010
run ts_m15   -0.015
run ts_m12   -0.012
run ts_m08   -0.008
run ts_m05   -0.005
run ts_000    0.0
run ts_p1256  0.001256
run ts_p05    0.005
# --- repeatability check: same config as ts_m10, run again ---
run ts_m10_rep -0.010

echo "=================================================================="
echo "### SWEEP COMPLETE $(date -Is)"
echo "=================================================================="
