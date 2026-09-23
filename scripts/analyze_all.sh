#!/bin/bash
# analyze_all.sh -- analyse every completed replay output dir
W=/home/orangepi/kswlt/vio_replay
BAG=/home/orangepi/vio_data/20260922T235522Z_LASEROFF3/bag
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=43
LIST="${1:-}"
if [ -z "$LIST" ]; then
  LIST=$(ls -1 $W/out/ 2>/dev/null)
fi
for L in $LIST; do
  D=$W/out/$L
  if [ ! -d "$D/odom" ]; then
    echo "######## SKIP $L (no odom bag) ########"
    continue
  fi
  echo "######## ANALYSIS $L ########"
  python3 $W/analyze2.py "$D" "$BAG" "$L" 2>&1 | grep -vE '^\[INFO\]'
  echo
done
echo "######## SUMMARY ########"
python3 - <<'PY'
import json, glob, os
rows = []
for p in sorted(glob.glob('/home/orangepi/kswlt/vio_replay/out/*/metrics2_*.json')):
    try:
        d = json.load(open(p))
    except Exception:
        continue
    d['_path'] = p
    rows.append(d)
hdr = ['label','span','closure_m','static_drift_m','max_jump_m','gt10cm',
       'path_len_m','rot_peak','rot_final','rot_first3','ba_abs_max','bg_abs_max']
print('%-13s %7s %10s %13s %10s %7s %10s %9s %10s %11s %10s %10s' % tuple(hdr))
for d in sorted(rows, key=lambda x: x.get('label','')):
    def g(k, f='%.4f'):
        v = d.get(k)
        return (f % v) if isinstance(v, (int, float)) else '-'
    print('%-13s %7s %10s %13s %10s %7s %10s %9s %10s %11s %10s %10s' % (
        d.get('label','?'), g('span','%.1f'), g('closure_m'), g('static_drift_m'),
        g('max_jump_m'), d.get('jumps_gt_10cm','-'), g('path_len_m'),
        g('rot_peak_excursion_m'), g('rot_final_excursion_m'),
        g('rot_first3s_excursion_m'), g('ba_abs_max','%.5f'), g('bg_abs_max','%.5f')))
print()
print('n_replays =', len(rows))
PY
