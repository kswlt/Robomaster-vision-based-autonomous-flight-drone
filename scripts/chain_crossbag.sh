#!/bin/bash
# chain_crossbag.sh -- after phase 2, verify the optimal config on OTHER bags.
# Guards against the timeshift optimum being an artefact of a single recording.
W=/home/orangepi/kswlt/vio_replay
echo "=== chain-crossbag started $(date -Is) ==="
while pgrep -f 'sweep_phase2\.sh' >/dev/null 2>&1; do
  sleep 15
done
echo "=== phase 2 finished $(date -Is) ==="
echo "--- phase 2 results ---"
bash "$W/analyze_all.sh" 2>&1 | tail -45
echo
echo "=== cross-bag verification with the optimal config ($(date -Is)) ==="
bash "$W/cross_bag_check.sh"
echo "=== chain-crossbag complete $(date -Is) ==="
