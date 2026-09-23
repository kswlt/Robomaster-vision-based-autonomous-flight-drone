#!/bin/bash
echo "########## A. WHAT IS server.py ? ##########"
for p in $(pgrep -f 'server.py'); do
  echo "--- pid $p ---"
  echo "  cmdline: $(tr '\0' ' ' < /proc/$p/cmdline)"
  echo "  cwd    : $(readlink /proc/$p/cwd)"
  echo "  exe    : $(readlink /proc/$p/exe)"
  echo "  fd1    : $(readlink /proc/$p/fd/1 2>/dev/null)"
  echo "  start  : $(ps -o lstart= -p $p)"
done
echo "--- listening ports of those pids ---"
ss -ltnp 2>/dev/null | head -20 || netstat -ltnp 2>/dev/null | head -20
echo
echo "########## B. STUCK ros2 CLI PROCESSES ##########"
ps -eo pid,etime,args | grep -E 'ros2 (param|topic|node|service|bag)' | grep -v grep
echo
echo "########## C. KILL STUCK ros2 CLI + daemon ##########"
pkill -KILL -f 'ros2 param' 2>/dev/null
pkill -KILL -f 'ros2cli.daemon' 2>/dev/null
pkill -KILL -f 'ros2-daemon' 2>/dev/null
sleep 2
rm -rf /home/orangepi/.ros/daemon 2>/dev/null
ps -eo pid,args | grep -Ei 'ros2|server.py' | grep -v grep || echo "(none left)"
echo
echo "########## D. CREATE CLEAN REPLAY WORKSPACE ##########"
W=/home/orangepi/kswlt/vio_replay
mkdir -p $W/configs $W/logs $W/out
ls -la $W
echo
echo "########## E. IDLE STATE ##########"
uptime
nproc
free -m
echo "--- top cpu now ---"
ps -eo pid,pcpu,pmem,etime,args --sort=-pcpu | head -8
