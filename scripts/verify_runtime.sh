#!/bin/bash
# verify_runtime.sh -- post-start verification against the task acceptance checklist.
#
# Run after start_vio.sh has brought the stack up.  Everything here is measured,
# not assumed: rates come from live topics, the IMU clock quality comes from the
# per-packet diagnostic CSV the bridge now writes, and ZUPT effectiveness is
# counted from the estimator log.
#
# Usage: verify_runtime.sh [ROS_DOMAIN_ID] [sample_seconds]
set -o pipefail

WS=/home/orangepi/kswlt/vio_ws
LOG=${VIO_LOG_DIR:-/tmp/vio}
DOM=${1:-42}
SECS=${2:-20}

source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
export ROS_DOMAIN_ID="$DOM"
export ROS_LOCALHOST_ONLY=1
export RCUTILS_COLORIZED_OUTPUT=0

OVLOG="$LOG/openvins_latest.log"
BRLOG="$LOG/bridge_latest.log"
CSV=$(ls -t "$LOG"/imu_clock_diag_*.csv 2>/dev/null | head -1)

echo "############ RUNTIME VERIFICATION ############"
echo "  domain   = $DOM"
echo "  ov log   = $OVLOG"
echo "  bridge   = $BRLOG"
echo "  diag csv = $CSV"
echo

echo "=== 1. loaded configuration (what the estimator ACTUALLY used) ==="
if [ -f "$OVLOG" ]; then
  grep -a -E '^LOADED_CONFIG_PATH|^LOADED_CAMERA_IMU_TIME_OFFSET_SEC' "$OVLOG" | sed 's/^/  /'
  grep -a -E '^LOADED_CAMERA_[01]_INTRINSICS' "$OVLOG" | cut -c1-150 | sed 's/^/  /'
else
  echo "  MISSING $OVLOG -- is the estimator running?"
fi
echo

echo "=== 2. IMU bridge clock-mapping strategy ==="
if [ -f "$BRLOG" ]; then
  grep -a -E 'IMU时钟映射模式|bootstrap complete|IMU_CLOCK mode|final dt|arrival_offset|repairs=|clock_offset_final' "$BRLOG" | tail -20 | sed 's/^/  /'
else
  echo "  MISSING $BRLOG"
fi
echo

echo "=== 3. per-packet IMU timestamp quality (from $CSV) ==="
if [ -n "$CSV" ] && [ -f "$CSV" ]; then
python3 - "$CSV" <<'PY'
import sys, csv
p = sys.argv[1]
ao, dt, rep, gated, scale = [], [], 0, 0, []
n = 0
with open(p) as f:
    r = csv.DictReader(f)
    for row in r:
        n += 1
        try:
            ao.append(float(row['arrival_offset']))
        except Exception:
            pass
        if row['dt']:
            try:
                dt.append(float(row['dt']))
            except Exception:
                pass
        if row['repaired'] == '1':
            rep += 1
        if row['gated'] == '1':
            gated += 1
        try:
            scale.append(float(row['scale_ppm']))
        except Exception:
            pass

def st(v, name):
    if not v:
        print('  %-18s : no data' % name); return
    v2 = sorted(v); m = len(v2)
    q = lambda t: v2[min(m - 1, max(0, int(t * (m - 1))))]
    mean = sum(v2) / m
    var = sum((x - mean) ** 2 for x in v2) / m
    print('  %-18s : n=%d mean=%.9f std=%.9f min=%.9f p50=%.9f p95=%.9f p99=%.9f max=%.9f'
          % (name, m, mean, var ** 0.5, v2[0], q(.5), q(.95), q(.99), v2[-1]))

print('  packets sampled    : %d' % n)
print('  timestamp repairs  : %d (%.4f%%)  <-- must be 0 for a healthy mapping'
      % (rep, 100.0 * rep / max(1, n)))
print('  gated outliers     : %d (%.4f%%)' % (gated, 100.0 * gated / max(1, n)))
st(ao, 'arrival_offset')
st(dt, 'final dt')
if dt:
    nominal = 1.0 / 200.0
    bad = sum(1 for x in dt if x < 1e-4)
    print('  dt < 100us         : %d  <-- clamping would show up here' % bad)
    print('  implied rate       : %.3f Hz' % (1.0 / (sum(dt) / len(dt))))
if scale:
    print('  scale_ppm final    : %+.1f' % scale[-1])
PY
else
  echo "  no diagnostic CSV found (bridge running with imu_diag_enable:=false?)"
fi
echo

echo "=== 4. live topic rates (${SECS}s each) ==="
for t in /imu /camera/camera/infra1/image_rect_raw /camera/camera/infra2/image_rect_raw /odomimu; do
  echo -n "  $(printf '%-48s' $t): "
  out=$(timeout $((SECS + 8)) ros2 topic hz $t 2>/dev/null | grep -m1 'average rate' || true)
  if [ -n "$out" ]; then echo "$out"; else echo "(no data within $((SECS + 8))s)"; fi
done
echo

echo "=== 5. ZUPT effectiveness (counted, not assumed) ==="
if [ -f "$OVLOG" ]; then
  P=$(grep -a -c 'passed disparity' "$OVLOG" 2>/dev/null || echo 0)
  A=$(grep -a -c 'ZUPT\]: accepted' "$OVLOG" 2>/dev/null || echo 0)
  echo "  passed disparity : $P"
  echo "  accepted         : $A"
  if [ "$P" -gt 0 ] && [ "$A" -eq 0 ]; then
    echo "  !! ZUPT gate passes but nothing is ever accepted."
    echo "     Check zupt_chi2_multipler > 0 (0 means chi2_limit=0 -> permanent reject)."
  elif [ "$A" -gt 0 ]; then
    echo "  OK: ZUPT actually accepts updates."
  fi
  echo "  initialisation   : $(grep -a -c 'successful initialization' "$OVLOG" 2>/dev/null || echo 0) success, $(grep -a -c 'unable to select window' "$OVLOG" 2>/dev/null || echo 0) IMU-window failures"
else
  echo "  MISSING $OVLOG"
fi
echo

echo "=== 6. estimator compute headroom ==="
if [ -f "$OVLOG" ]; then
python3 - "$OVLOG" <<'PY'
import sys, re
ANSI = re.compile(r'\x1b\[[0-9;]*m')
tot, hz, behind = [], [], []
for ln in open(sys.argv[1], 'r', encoding='utf-8', errors='replace'):
    m = re.match(r'^\[TIME\]: ([\d.]+) seconds total \(([\d.]+) hz, ([\d.]+) ms behind\)', ANSI.sub('', ln).strip())
    if m:
        tot.append(float(m.group(1))); hz.append(float(m.group(2))); behind.append(float(m.group(3)))
if tot:
    v = sorted(tot); n = len(v)
    q = lambda t: v[min(n-1, max(0, int(t*(n-1))))]
    print('  per-frame CPU   : n=%d mean=%.4f s p50=%.4f p95=%.4f max=%.4f' % (n, sum(v)/n, q(.5), q(.95), v[-1]))
    print('  frame budget    : 0.0333 s (30 Hz). p50 above it means the estimator cannot keep up.')
    over = sum(1 for x in v if x > 0.0333)
    print('  frames over budget: %d / %d = %.1f%%' % (over, n, 100.0*over/n))
    b = sorted(behind)
    print('  reported "behind": p50=%.2f p95=%.2f  (source multiplies by 100.0, so x10 = ms)' % (b[len(b)//2], b[int(.95*(len(b)-1))]))
PY
else
  echo "  MISSING $OVLOG"
fi
echo

echo "=== 7. system load ==="
uptime | sed 's/^/  /'
nproc | sed 's/^/  cores: /'
ps -eo pid,pcpu,pmem,etime,args --sort=-pcpu 2>/dev/null | head -8 | sed 's/^/  /'
echo
echo "############ VERIFICATION COMPLETE ############"
