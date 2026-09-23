#!/bin/bash
# FREEZE all evidence of the current (pre-change) runtime, then stop the stack.
set -u
TS=$(date +%Y%m%dT%H%M%S)
EV=/home/orangepi/vio_audit_freeze_$TS
mkdir -p "$EV"
echo "EVIDENCE_DIR=$EV"

RUN=/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430

echo "########## 1. PROCESS / SYSTEM STATE ##########"
{
  echo "=== date ==="; date -Is
  echo "=== uname ==="; uname -a
  echo "=== uptime ==="; uptime
  echo "=== nproc ==="; nproc
  echo "=== mem ==="; free -m
  echo "=== ps (vio related) ==="
  ps -eo pid,ppid,pcpu,pmem,etime,lstart,args | grep -Ei 'run_subscribe|vio_bridge|foxglove|realsense|odom_|viz_web' | grep -v grep
  echo "=== systemd vio/camera/watchdog ==="
  systemctl status vio.service --no-pager 2>&1 | head -20
  systemctl is-enabled vio.service 2>&1
  systemctl is-active vio.service 2>&1
  systemctl is-enabled vio-watchdog.service 2>&1
  systemctl is-enabled watchdog_camera.service 2>&1
  echo "=== lsusb -t ==="; lsusb -t
  echo "=== lsusb ==="; lsusb
  echo "=== thermal ==="; for z in /sys/class/thermal/thermal_zone*/temp; do echo "$z $(cat $z 2>/dev/null)"; done
  echo "=== cpufreq ==="; for c in /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq; do echo "$c $(cat $c 2>/dev/null)"; done
  echo "=== dmesg usb/video last 60 ==="; dmesg 2>/dev/null | grep -Ei 'usb|uvc|video|xhci' | tail -60
} > "$EV/system_state.txt" 2>&1
echo "  -> system_state.txt"

echo "########## 2. CONFIG SNAPSHOT (running config dir, incl. all .bak) ##########"
mkdir -p "$EV/config_d430_running"
cp -a "$RUN"/. "$EV/config_d430_running"/ 2>/dev/null
ls -la "$EV/config_d430_running" > "$EV/config_d430_running_ls.txt" 2>&1

echo "########## 3. SCRIPTS / SERVICES SNAPSHOT ##########"
mkdir -p "$EV/scripts"
for f in \
  /home/orangepi/kswlt/vio_ws/start_vio.sh \
  /home/orangepi/kswlt/vio_ws/run_vio.sh \
  /home/orangepi/kswlt/vio_ws/vio_bridge/vio_bridge_combined.py \
  /home/orangepi/kswlt/gh_d430/start_vio.sh \
  /home/orangepi/kswlt/gh_d430/start_vio_systemd.sh \
  /home/orangepi/kswlt/tools/start_vio.sh \
  /home/orangepi/kswlt/tools/start_vio_systemd.sh \
  /home/orangepi/kswlt/tools/watchdog_camera.sh \
  /home/orangepi/kswlt/vio-improve/watchdog_camera.sh \
  /home/orangepi/kswlt/vio-improve/start_vio_systemd.sh \
  /home/orangepi/kswlt/vio-improve/start_vio.sh \
  /etc/systemd/system/vio.service \
  /etc/systemd/system/vio-watchdog.service \
  /etc/systemd/system/watchdog_camera.service ; do
  if [ -f "$f" ]; then
    base=$(echo "$f" | tr '/' '_')
    cp -a "$f" "$EV/scripts/$base"
  fi
done
ls -la "$EV/scripts" > "$EV/scripts_ls.txt" 2>&1

echo "########## 4. HASHES ##########"
{
  echo "=== running config dir ==="
  sha256sum "$RUN"/* 2>&1
  echo "=== scripts ==="
  find /home/orangepi/kswlt/vio_ws /home/orangepi/kswlt/gh_d430 /home/orangepi/kswlt/tools /home/orangepi/kswlt/vio-improve /etc/systemd/system -maxdepth 2 \
    \( -name 'start_vio*.sh' -o -name 'run_vio.sh' -o -name 'vio_bridge_combined.py' -o -name 'watchdog_camera.sh' -o -name 'vio*.service' \) \
    -exec sha256sum {} \; 2>/dev/null
  echo "=== openvins source key files ==="
  sha256sum \
    /home/orangepi/kswlt/vio_ws/src/open_vins/ov_msckf/src/update/UpdaterZeroVelocity.cpp \
    /home/orangepi/kswlt/vio_ws/src/open_vins/ov_msckf/src/update/UpdaterZeroVelocity.h \
    /home/orangepi/kswlt/vio_ws/src/open_vins/ov_msckf/src/core/VioManager.cpp \
    /home/orangepi/kswlt/vio_ws/src/open_vins/ov_msckf/src/ros/ROS2Visualizer.cpp \
    /home/orangepi/kswlt/vio_ws/src/open_vins/ov_init/src/static/StaticInitializer.cpp \
    /home/orangepi/kswlt/vio_ws/src/open_vins/ov_msckf/src/run_subscribe_msckf.cpp \
    2>&1
  echo "=== built binary ==="
  sha256sum /home/orangepi/kswlt/vio_ws/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf 2>&1
} > "$EV/hashes.txt" 2>&1

echo "########## 5. RUNTIME LOGS ##########"
cp -a /tmp/vio_audit.log "$EV/vio_audit.log" 2>/dev/null
cp -a /tmp/vio_bridge_audit.log "$EV/vio_bridge_audit.log" 2>/dev/null
cp -a /tmp/foxglove.log "$EV/foxglove.log" 2>/dev/null
ls -la "$EV" > "$EV/_ls.txt" 2>&1

echo "########## 6. STOP THE STACK (SIGINT first, then KILL) ##########"
pkill -INT -f 'run_subscribe_msckf' 2>/dev/null
pkill -INT -f 'vio_bridge_combined' 2>/dev/null
pkill -INT -f 'foxglove_bridge' 2>/dev/null
pkill -INT -f 'odom_to_path' 2>/dev/null
pkill -INT -f 'odom_throttle' 2>/dev/null
pkill -INT -f 'viz_web' 2>/dev/null
sleep 4
pkill -TERM -f 'run_subscribe_msckf' 2>/dev/null
pkill -TERM -f 'vio_bridge_combined' 2>/dev/null
pkill -TERM -f 'foxglove_bridge' 2>/dev/null
pkill -TERM -f 'realsense2_camera' 2>/dev/null
sleep 3
pkill -KILL -f 'run_subscribe_msckf' 2>/dev/null
pkill -KILL -f 'vio_bridge_combined' 2>/dev/null
pkill -KILL -f 'foxglove_bridge' 2>/dev/null
pkill -KILL -f 'realsense2_camera' 2>/dev/null
sleep 3
echo "=== remaining related processes ==="
ps -eo pid,args | grep -Ei 'run_subscribe|vio_bridge|foxglove|realsense' | grep -v grep || echo "(none)"
echo "=== after-stop state ==="
uptime
pkill -f 'ros2 daemon' 2>/dev/null
rm -rf /home/orangepi/.ros/daemon 2>/dev/null
echo "STOP DONE"

echo "########## 7. PACKAGE ##########"
cd /home/orangepi
tar czf "$EV.tar.gz" -C /home/orangepi "$(basename $EV)" 2>/dev/null
ls -la "$EV.tar.gz"
echo "PACKAGE=$EV.tar.gz"
