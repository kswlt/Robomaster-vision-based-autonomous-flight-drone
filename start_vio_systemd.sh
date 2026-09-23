#!/bin/bash
# ============================================================================
#  systemd wrapper for the D430 VIO stack.
#
#  This script deliberately contains NO startup logic of its own.  It used to
#  duplicate the launch sequence, and the two copies diverged: the manual script
#  tried to pass enable_ir_emitter (an argument that does not exist in this
#  realsense-ros build) while the systemd copy did not attempt to disable the
#  projector at all, so "IR off" experiments never applied to the real service.
#
#  All differences are now impossible by construction: everything happens in
#  start_vio.sh, including the precheck that refuses to start the estimator.
#
#  Retained here: fault-latch and single-instance locking, which are
#  systemd-specific concerns.
# ============================================================================
set -o pipefail

FAULT_LATCH="${VIO_FAULT_LATCH:-/tmp/vio_fault_latched}"
RESTART_LOG="${VIO_RESTART_LOG:-/tmp/vio_restart.log}"
LOCK_FILE="${VIO_LOCK_FILE:-/tmp/vio_restart.lock}"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
DOMAIN="${VIO_ROS_DOMAIN_ID:-42}"

log() { echo "[$(date -Is)] $*" >> "$RESTART_LOG"; }

if [ -f "$FAULT_LATCH" ]; then
    log "检测到VIO故障锁存，拒绝自动启动；人工确认后删除 $FAULT_LATCH"
    exit 0
fi

exec 9>"$LOCK_FILE"
flock -n 9 || { log "已有VIO实例在运行，退出"; exit 0; }

# wait for USB devices to settle after boot
sleep 3

START="$SELF_DIR/start_vio.sh"
if [ ! -x "$START" ]; then
    log "找不到可执行的 $START"
    exit 1
fi

log "启动 VIO（委托给 start_vio.sh --systemd, domain=$DOMAIN）"

# Foreground: systemd follows this process, and start_vio.sh waits on its
# children, so the service lifetime still tracks the estimator.
VIO_LOG_DIR="${VIO_LOG_DIR:-/var/log/vio}" VIO_RUN_DIR="${VIO_RUN_DIR:-/run/vio}" \
    bash "$START" --systemd -d "$DOMAIN"
RC=$?

log "VIO 退出，退出码: $RC，等待 systemd 重启..."
exit $RC
