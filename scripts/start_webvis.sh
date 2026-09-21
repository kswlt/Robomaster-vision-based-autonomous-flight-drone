#!/bin/bash
# E2E-RL web_vis launcher (training-consistent chain)
cd /home/orangepi/kswlt_e2d
export E2E_MAX_SPEED=1.0  # test-flight speed cap (safety layer); raise after bench flights
export E2E_RECORD_CSV=/home/orangepi/kswlt_e2d/flight_data.csv  # flight diagnostics (Level 4 replay)
pkill -9 -f web_vis.py 2>/dev/null
sleep 2
nohup python3 -u web_vis.py --port 8080 > web_vis.log 2>&1 &
echo "PID=$!"
sleep 4
ps aux | grep web_vis | grep -v grep | head -1
echo "---LOG---"
head -10 web_vis.log
echo "---STATUS TEST---"
curl -s --max-time 3 http://127.0.0.1:8080/status | head -c 200
echo ""