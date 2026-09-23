#!/bin/bash
# chain_sweeps.sh -- wait for the running timeshift sweep, then run the extension.
# Avoids idle polling between two long deterministic replay batches.
W=/home/orangepi/kswlt/vio_replay
echo "=== chain started $(date -Is) ==="
while pgrep -f 'sweep_timeshift\.sh' >/dev/null 2>&1; do
  sleep 15
done
echo "=== primary timeshift sweep finished $(date -Is) ==="
bash "$W/sweep_timeshift_ext.sh"
echo "=== extension finished, analysing everything $(date -Is) ==="
bash "$W/analyze_all.sh" 2>&1 | tail -30
echo "=== chain complete $(date -Is) ==="
