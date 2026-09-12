#!/bin/bash
# 相机健康看门狗 daemon（10秒级检测）
# 检测到camera.log报错（帧超时/连接超时/设备丢失/节点异常）→ 重启vio.service
# 冷却60秒：给重启留出初始化时间，防止重启风暴
LOG=/tmp/camera.log
LOCK=/tmp/watchdog_last_restart
LOG_FRESH_WINDOW=30

while true; do
  if [ -f "$LOG" ]; then
    # 冷却检查：上次重启60秒内不重复触发
    if [ -f "$LOCK" ]; then
      LAST=$(cat "$LOCK")
      NOW=$(date +%s)
      if [ $((NOW - LAST)) -lt 180 ]; then
        sleep 10
        continue
      fi
    fi
    # 日志在近30秒内持续更新 且 尾部有相机错误 → 相机流挂了
    LOG_AGE=$(( $(date +%s) - $(stat -c %Y "$LOG") ))
    if [ "$LOG_AGE" -lt "$LOG_FRESH_WINDOW" ] && tail -4 "$LOG" | grep -qE "Frames didn.t arrived|Connection timed out|NOT found. Will Try again|failed with exception"; then
      echo "$(date '+%F %T') 相机异常(日志${LOG_AGE}s前更新)，重启vio.service" >> /tmp/watchdog.log
      date +%s > "$LOCK"
      sudo systemctl restart vio.service
    fi
  fi
  sleep 10
done
