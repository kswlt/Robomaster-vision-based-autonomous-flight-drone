#!/bin/bash
# chain_phase2.sh -- wait for the extension sweep, then run phase 2.
# Keeps the board busy on deterministic replay work without idle polling.
W=/home/orangepi/kswlt/vio_replay
echo "=== chain-phase2 started $(date -Is) ==="
while pgrep -f 'sweep_timeshift_ext\.sh' >/dev/null 2>&1; do
  sleep 15
done
echo "=== extension sweep finished $(date -Is) ==="
echo "--- extension results ---"
bash "$W/analyze_all.sh" 'ext_m18 ext_m20 ext_m24 ext_m30 ts_m12 ts_m15' 2>&1 | tail -12
echo
echo "=== starting phase 2 ($(date -Is)) ==="
bash "$W/sweep_phase2.sh"
echo "=== chain-phase2 complete $(date -Is) ==="
