#!/bin/bash
# VIO链路健康看门狗（10秒级检测）
# 相机/进程暂态异常时重启；VIO发散时锁存停机，禁止重启后重复注入。
# Log paths MUST match start_vio.sh (VIO_LOG_DIR default /tmp/vio, with
# *_latest.log symlinks). /tmp/camera.log and /tmp/vio_bridge.log are stale
# paths from an older layout and made the watchdog blind to real failures.
VIO_LOG_DIR="${VIO_LOG_DIR:-/tmp/vio}"
CAMERA_LOG="${CAMERA_LOG:-$VIO_LOG_DIR/camera_latest.log}"
BRIDGE_LOG="${BRIDGE_LOG:-$VIO_LOG_DIR/bridge_latest.log}"
LOCK=/tmp/watchdog_last_restart
LOG_FRESH_WINDOW=30
RESTART_COOLDOWN=180
STARTUP_GRACE=30
FAULT_LATCH=/tmp/vio_fault_latched

restart_vio() {
  local reason="$1"
  echo "$(date '+%F %T') ${reason}，重启vio.service" >> /tmp/watchdog.log
  date +%s > "$LOCK"
  systemctl restart vio.service
}

latch_vio_fault() {
  local reason="$1"
  echo "$(date '+%F %T') ${reason}，锁存故障并停止vio.service" >> /tmp/watchdog.log
  echo "$(date '+%F %T') ${reason}" > "$FAULT_LATCH"
  systemctl stop vio.service
}

while true; do
  # 尊重人工停止，不把inactive服务擅自拉起。
  if ! systemctl is-active --quiet vio.service; then
    sleep 10
    continue
  fi

  NOW=$(date +%s)
  if [ -f "$LOCK" ]; then
    LAST=$(cat "$LOCK")
    if [ $((NOW - LAST)) -lt "$RESTART_COOLDOWN" ]; then
      sleep 10
      continue
    fi
  fi

  # Use systemd's actual activation time for startup grace. A log-file mtime is
  # stale during the launch script's initial USB waits and can cause a false
  # restart before the camera and bridge processes have even been spawned.
  START_AGE=0
  ACTIVE_USEC=$(systemctl show -p ActiveEnterTimestampMonotonic --value vio.service 2>/dev/null)
  SYSTEM_UPTIME_S=$(cut -d. -f1 /proc/uptime)
  if [[ "$ACTIVE_USEC" =~ ^[0-9]+$ ]] && [ "$ACTIVE_USEC" -gt 0 ]; then
    START_AGE=$((SYSTEM_UPTIME_S - ACTIVE_USEC / 1000000))
  fi

  if [ -f "$CAMERA_LOG" ]; then
    CAMERA_LOG_AGE=$((NOW - $(stat -c %Y "$CAMERA_LOG")))
    if [ "$CAMERA_LOG_AGE" -lt "$LOG_FRESH_WINDOW" ] && \
       tail -20 "$CAMERA_LOG" | grep -qE "Frames didn.t arrived|Connection timed out|NOT found. Will Try again|failed with exception"; then
      restart_vio "相机数据流异常(日志${CAMERA_LOG_AGE}s前更新)"
      sleep 10
      continue
    fi
  fi

  if [ -f "$BRIDGE_LOG" ]; then
    BRIDGE_LOG_AGE=$((NOW - $(stat -c %Y "$BRIDGE_LOG")))
    if [ "$BRIDGE_LOG_AGE" -lt "$LOG_FRESH_WINDOW" ] && \
       tail -200 "$BRIDGE_LOG" | grep -q "VIO_FATAL:"; then
      latch_vio_fault "桥接健康门控触发"
      sleep 10
      continue
    fi
    if [ "$START_AGE" -gt "$STARTUP_GRACE" ] && [ "$BRIDGE_LOG_AGE" -gt "$LOG_FRESH_WINDOW" ]; then
      restart_vio "桥接日志停止更新(${BRIDGE_LOG_AGE}s)"
      sleep 10
      continue
    fi
  fi

  if [ "$START_AGE" -gt "$STARTUP_GRACE" ]; then
    if ! pgrep -f 'realsense2_camera_node' >/dev/null || \
       ! pgrep -f 'vio_bridge_combined.py' >/dev/null || \
       ! pgrep -f 'install/ov_msckf/lib/ov_msckf/run_subscribe_msckf' >/dev/null; then
      restart_vio "关键进程缺失"
      sleep 10
      continue
    fi
  fi
  sleep 10
done
