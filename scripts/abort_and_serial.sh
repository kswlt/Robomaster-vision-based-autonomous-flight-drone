#!/bin/bash
# Abort all concurrent replay work, then rerun phase 2 and the cross-bag check
# strictly serially under a lock.
#
# Why this is needed: chain_crossbag.sh waited on `pgrep -f sweep_phase2.sh`,
# but at the moment it started, phase 2 had not yet begun, so pgrep returned
# empty, the wait loop exited immediately, and the cross-bag replays started
# concurrently with phase 2.  Two estimators on the same ROS_DOMAIN_ID fight over
# the same topics, and replay_one.sh starts by killing every run_subscribe_msckf,
# so each run was destroying the other.  Those results are void.
set -o pipefail

W=/home/orangepi/kswlt/vio_replay
LOG=$W/logs
echo "=== ABORT CONCURRENT REPLAYS $(date -Is) ==="
pkill -KILL -f 'chain_phase2.sh' 2>/dev/null
pkill -KILL -f 'chain_crossbag.sh' 2>/dev/null
pkill -KILL -f 'sweep_phase2.sh' 2>/dev/null
pkill -KILL -f 'cross_bag_check.sh' 2>/dev/null
pkill -KILL -f 'replay_one.sh' 2>/dev/null
pkill -KILL -f 'run_subscribe_msckf' 2>/dev/null
pkill -KILL -f 'ros2 bag play' 2>/dev/null
pkill -KILL -f 'ros2 bag record' 2>/dev/null
sleep 4
echo "--- remaining ---"
pgrep -af 'replay_one|run_subscribe|bag play|bag record|sweep_phase2|cross_bag|chain_' | grep -v 'bash -c' || echo "(none)"

echo
echo "=== VOID the contaminated runs ==="
for d in /home/orangepi/kswlt/vio_replay/out/zupt_* \
         /home/orangepi/kswlt/vio_replay/out/init_d* \
         /home/orangepi/kswlt/vio_replay/out/xb_* ; do
  if [ -d "$d" ]; then
    mv "$d" "$d.VOID-concurrent"
    rm -f "/home/orangepi/kswlt/vio_replay/out/metrics2_$(basename $d).json"
    echo "  voided $d"
  fi
done
ls -1 $W/out/ | tr '\n' ' '
echo

echo
echo "=== restart STRICTLY SERIAL: phase2 then crossbag, under one lock ==="
cat > $W/run_serial_final.sh <<'EOS'
#!/bin/bash
set -o pipefail
W=/home/orangepi/kswlt/vio_replay
LOG=$W/logs
exec 9>/tmp/vio_replay.lock
flock -n 9 || { echo "another replay run holds the lock; refusing to start"; exit 1; }

echo "=== SERIAL BATCH START $(date -Is) (lock held) ==="

echo "--- phase 2: ZUPT + init A/B ---"
bash $W/sweep_phase2.sh
echo "--- phase 2 done $(date -Is) ---"

echo "--- cross-bag check with the optimal config ---"
bash $W/cross_bag_check.sh
echo "--- cross-bag done $(date -Is) ---"

echo "--- final analysis ---"
bash $W/analyze_all.sh 2>&1 | tail -50
echo "=== SERIAL BATCH COMPLETE $(date -Is) ==="
EOS
chmod +x $W/run_serial_final.sh
nohup bash $W/run_serial_final.sh > $LOG/run_serial_final.txt 2>&1 &
echo "SERIAL_BATCH_STARTED pid=$!"
date -Is
