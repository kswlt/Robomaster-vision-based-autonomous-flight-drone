#!/bin/bash
# cross_bag_check.sh -- does one fixed config behave consistently across bags?
#
# The timeshift sweep only ever used one bag.  Config repeatability claims need
# at least one independent recording, otherwise the "optimum" could be fitted to
# that single bag's quirks.  This replays the currently-best config on the other
# immutable bags and reports the same metrics.
W=/home/orangepi/kswlt/vio_replay
D=/home/orangepi/vio_data
DOM=43
# default: the config that won the timeshift sweep (timeshift = -0.015)
CFG=${1:-$W/configs/base_best}

echo "=== cross-bag check using config $CFG ==="
echo "  $(grep -h timeshift_cam_imu $CFG/kalibr_imucam_chain.yaml)"
echo "  $(grep -h zupt_chi2_multipler $CFG/estimator_config.yaml)"

run_one () {
  local name=$1 ; local bag=$2
  echo "=================================================================="
  echo "### CROSS $name   bag=$bag"
  echo "###       $(date -Is)"
  echo "=================================================================="
  rm -rf "$W/out/$name"
  bash $W/replay_one.sh "$bag" "$CFG" "$W/out/$name" "$name" $DOM
  echo "### CROSS $name done"
}

run_one xb_laseroff   $D/20260922T194503Z_LASEROFF/bag
run_one xb_laseroff2  $D/20260922T195104Z_LASEROFF2/bag
run_one xb_dyn50      $D/20260922T180933_210Z_DYN50/bag
run_one xb_dyn50b     $D/20260922T185550_238Z_DYN50B/bag

echo "=================================================================="
echo "### CROSS-BAG COMPLETE $(date -Is)"
echo "=================================================================="
bash $W/analyze_all.sh 2>&1 | tail -30
