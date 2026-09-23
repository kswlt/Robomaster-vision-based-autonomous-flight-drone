#!/bin/bash
# sweep_phase2.sh -- ZUPT semantics and static-initialisation A/B on ONE immutable bag.
# One variable per run; identical code and identical bag throughout.
W=/home/orangepi/kswlt/vio_replay
BAG=/home/orangepi/vio_data/20260922T235522Z_LASEROFF3/bag
BASE=$W/configs/base            # timeshift -0.010, zupt_chi2_multipler 0 (broken)
DOM=43

run () {
  local name=$1 ; shift
  echo "=================================================================="
  echo "### PHASE2 $name   $(date -Is)"
  echo "  overrides: $*"
  echo "=================================================================="
  python3 $W/mksweep.py "$BASE" "$W/configs/$name" "$@" || return 1
  rm -rf "$W/out/$name"
  bash $W/replay_one.sh "$BAG" "$W/configs/$name" "$W/out/$name" "$name" $DOM
  echo "### PHASE2 $name done"
}

# --- F: ZUPT semantics, starting from the broken baseline value already measured ---
# F1 broken reference re-run with the SAME (0) value -> repeatability anchor
run zupt_m0    zupt_chi2_multipler=0
# F2 correct semantics: both gates must pass, chi2 multiplier enabled
run zupt_m1    zupt_chi2_multipler=1
# F3 extremely permissive chi2 gate (upper bound on how much ZUPT can help)
run zupt_m10   zupt_chi2_multipler=10
# F4 ZUPT fully off, as a control for "does ZUPT matter at all here"
run zupt_off   try_zupt=false

# --- C: static initialisation threshold ---
run init_d03   init_max_disparity=0.3
run init_d10   init_max_disparity=10.0

echo "=================================================================="
echo "### PHASE2 COMPLETE $(date -Is)"
echo "=================================================================="
