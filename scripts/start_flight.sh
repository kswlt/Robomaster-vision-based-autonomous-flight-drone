#!/bin/bash
cd /home/orangepi/kswlt_e2d
pkill -9 -f "python3 main.py" 2>/dev/null
sleep 2
nohup python3 -u main.py --mode ground --foxglove-port 8766 --sim-depth > flight.log 2>&1 &
echo "Started PID: $!"
sleep 8
echo "=== LOG ==="
cat flight.log
echo "=== PROC ==="
ps aux | grep "python3 main" | grep -v grep
echo "=== PORT ==="
ss -tlnp | grep 8766
