#!/bin/bash
# ============================================================================
#  D430 stereo + PX4 IMU + OpenVINS  —— 唯一权威启动脚本
#
#  This is the ONLY supported entry point.  start_vio_systemd.sh is a thin
#  wrapper around it, so the manual and systemd paths cannot diverge again.
#
#  Startup order (and why):
#    1. print CONFIG_SHA256 of every file that can change the estimate
#    2. hardware precheck (D430 present, USB3 SuperSpeed, PX4 serial)
#    3. force IR emitter OFF + laser_power=0 and VERIFY on the hardware
#    4. start RealSense (848x480x30, infra1+infra2, depth/colour off)
#    5. camera precheck (resolution, intrinsics == YAML, rate, stereo sync,
#       emitter still off).  Any critical failure aborts BEFORE the estimator.
#    6. start the IMU bridge (send_vision_to_px4 stays false)
#    7. IMU precheck (rate, monotonic timestamps, no micro-dt clamping)
#    8. start OpenVINS
#    9. print the stationary-initialisation requirement
#
#  Usage:
#    ./start_vio.sh [-d ROS_DOMAIN_ID] [-c CONFIG_DIR] [--foxglove] [--systemd]
# ============================================================================
set -o pipefail

WS="$HOME/kswlt/vio_ws"
CONFIG_DIR="$WS/src/open_vins/config/d430"
DOMAIN=42
ENABLE_FOXGLOVE=0
SYSTEMD_MODE=0
LOG_DIR="${VIO_LOG_DIR:-/tmp/vio}"
RUN_DIR="${VIO_RUN_DIR:-/tmp/vio}"
SEND_VISION_TO_PX4=false          # 必须保持 false，直到 VIO 动态验收通过
IMU_CLOCK_MODE=slow
CAMERA_PROFILE=848x480x30
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    -d) DOMAIN="$2"; shift 2 ;;
    -c) CONFIG_DIR="$2"; shift 2 ;;
    --foxglove) ENABLE_FOXGLOVE=1; shift ;;
    --systemd) SYSTEMD_MODE=1; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR" "$RUN_DIR"
STAMP=$(date +%Y%m%dT%H%M%S)
OV_LOG="$LOG_DIR/openvins_$STAMP.log"
CAM_LOG="$LOG_DIR/camera_$STAMP.log"
BRIDGE_LOG="$LOG_DIR/bridge_$STAMP.log"
CONSOLE="$LOG_DIR/startup_$STAMP.log"
ln -sfn "$OV_LOG" "$LOG_DIR/openvins_latest.log"
ln -sfn "$BRIDGE_LOG" "$LOG_DIR/bridge_latest.log"
ln -sfn "$CAM_LOG" "$LOG_DIR/camera_latest.log"

exec > >(tee -a "$CONSOLE") 2>&1

echo "============================================================"
echo " D430 VIO startup   $(date -Is)"
echo "   mode               = $([ $SYSTEMD_MODE -eq 1 ] && echo systemd || echo manual)"
echo "   workspace          = $WS"
echo "   config_dir         = $CONFIG_DIR"
echo "   ros_domain         = $DOMAIN   (ROS_LOCALHOST_ONLY=1, matches existing nodes)"
echo "   foxglove           = $([ $ENABLE_FOXGLOVE -eq 1 ] && echo 'ON' || echo 'OFF (estimator data path has priority)')"
echo "   send_vision_to_px4 = $SEND_VISION_TO_PX4"
echo "   imu_clock_mode     = $IMU_CLOCK_MODE"
echo "   camera_profile     = $CAMERA_PROFILE"
echo "============================================================"

# ---------------------------------------------------------------- environment
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
export ROS_DOMAIN_ID="$DOMAIN"
export ROS_LOCALHOST_ONLY=1
export RCUTILS_COLORIZED_OUTPUT=0

for cand in "$SELF_DIR/scripts/vio_precheck.py" \
            "$WS/scripts/vio_precheck.py" \
            "$HOME/kswlt/vio_replay/vio_precheck.py"; do
  if [ -f "$cand" ]; then PRECHECK="$cand"; break; fi
done
if [ -z "${PRECHECK:-}" ]; then
  echo "PRECHECK FAIL: scripts/vio_precheck.py not found (looked next to $SELF_DIR)"
  exit 1
fi
echo "precheck script: $PRECHECK"

# ------------------------------------------------------------- config hashes
echo
echo "---- CONFIG_SHA256 (exact files the estimator and bridge will load) ----"
for f in "$CONFIG_DIR/estimator_config.yaml" \
         "$CONFIG_DIR/kalibr_imu_chain.yaml" \
         "$CONFIG_DIR/kalibr_imucam_chain.yaml"; do
  if [ -f "$f" ]; then
    printf 'CONFIG_SHA256 %s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
  else
    echo "PRECHECK FAIL: missing $f"
    exit 1
  fi
done
BRIDGE_PY="$WS/vio_bridge/vio_bridge_combined.py"
MAPPER_PY="$WS/vio_bridge/imu_clock_mapper.py"
for f in "$BRIDGE_PY" "$MAPPER_PY"; do
  if [ -f "$f" ]; then
    printf 'CONFIG_SHA256 %s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
  else
    echo "PRECHECK FAIL: missing $f"
    exit 1
  fi
done
echo "TIMESHIFT_IN_FILE $(grep -h timeshift_cam_imu "$CONFIG_DIR/kalibr_imucam_chain.yaml" | head -1 | tr -d ' ')"

# -------------------------------------------------------- stage 1: hardware
echo
echo "########## STAGE 1/6: hardware precheck ##########"
python3 "$PRECHECK" hw "$CONFIG_DIR" "$DOMAIN" || {
  echo "PRECHECK FAIL: hardware stage failed -- estimator NOT started"
  exit 1
}

cleanup() {
  echo "[$(date -Is)] stopping VIO stack..."
  for pf in "$RUN_DIR"/camera.pid "$RUN_DIR"/bridge.pid "$RUN_DIR"/openvins.pid "$RUN_DIR"/foxglove.pid; do
    [ -f "$pf" ] || continue
    pid=$(cat "$pf" 2>/dev/null)
    [ -n "$pid" ] && kill -INT "$pid" 2>/dev/null
  done
  sleep 3
  pkill -INT -f 'run_subscribe_msckf' 2>/dev/null
  pkill -INT -f 'vio_bridge_combined' 2>/dev/null
  pkill -INT -f 'realsense2_camera' 2>/dev/null
  sleep 3
  pkill -KILL -f 'run_subscribe_msckf' 2>/dev/null
  pkill -KILL -f 'vio_bridge_combined' 2>/dev/null
  pkill -KILL -f 'realsense2_camera' 2>/dev/null
  rm -f "$RUN_DIR"/*.pid
}
trap cleanup EXIT INT TERM

# ----------------------------------------------------------- stage 2: camera
echo
echo "########## STAGE 2/6: RealSense (${CAMERA_PROFILE}, infra1+infra2, no depth/colour) ##########"
echo "NOTE: this realsense-ros build has NO enable_ir_emitter launch argument."
echo "      The projector is disabled on the HARDWARE and verified, not assumed."
ros2 launch realsense2_camera rs_launch.py \
    camera_name:=camera \
    camera_namespace:=camera \
    enable_depth:=false \
    enable_color:=false \
    enable_infra1:=true \
    enable_infra2:=true \
    enable_sync:=false \
    pointcloud.enable:=false \
    depth_module.infra_profile:=$CAMERA_PROFILE \
    > "$CAM_LOG" 2>&1 &
echo $! > "$RUN_DIR/camera.pid"
echo "camera pid=$(cat "$RUN_DIR/camera.pid")  log=$CAM_LOG"

for i in $(seq 1 30); do
  sleep 1
  if grep -q 'RealSense Node Is Up' "$CAM_LOG" 2>/dev/null; then
    echo "camera node ready after ${i}s"
    break
  fi
done
sleep 3

echo
echo "########## STAGE 3/6: camera precheck (incl. emitter re-verification) ##########"
python3 "$PRECHECK" camera "$CONFIG_DIR" "$DOMAIN" || {
  echo "PRECHECK FAIL: camera stage failed -- estimator NOT started"
  exit 1
}

# ----------------------------------------------------------- stage 4: bridge
echo
echo "########## STAGE 4/6: IMU bridge (PX4 -> /imu) ##########"
python3 "$BRIDGE_PY" --ros-args \
    -p serial_port:=/dev/ttyACM0 \
    -p send_vision_to_px4:=$SEND_VISION_TO_PX4 \
    -p imu_clock_mode:=$IMU_CLOCK_MODE \
    -p imu_diag_enable:=true \
    -p imu_diag_csv:="$LOG_DIR/imu_clock_diag_$STAMP.csv" \
    > "$BRIDGE_LOG" 2>&1 &
echo $! > "$RUN_DIR/bridge.pid"
echo "bridge pid=$(cat "$RUN_DIR/bridge.pid")  log=$BRIDGE_LOG"
sleep 8

echo
echo "########## STAGE 5/6: IMU precheck ##########"
python3 "$PRECHECK" imu "$CONFIG_DIR" "$DOMAIN" || {
  echo "PRECHECK FAIL: IMU stage failed -- estimator NOT started"
  exit 1
}

# --------------------------------------------------------- stage 6: OpenVINS
echo
echo "########## STAGE 6/6: OpenVINS MSCKF ##########"
"$WS/install/ov_msckf/lib/ov_msckf/run_subscribe_msckf" \
    --ros-args \
    -p config_path:="$CONFIG_DIR/estimator_config.yaml" \
    -p publish_tf:=false \
    > "$OV_LOG" 2>&1 &
echo $! > "$RUN_DIR/openvins.pid"
echo "openvins pid=$(cat "$RUN_DIR/openvins.pid")  log=$OV_LOG"

if [ $ENABLE_FOXGLOVE -eq 1 ]; then
  ros2 run foxglove_bridge foxglove_bridge --ros-args \
      -p topic_filter:="[/odomimu_viz,/trajectory,/tf_static]" \
      > "$LOG_DIR/foxglove_$STAMP.log" 2>&1 &
  echo $! > "$RUN_DIR/foxglove.pid"
  echo "foxglove pid=$(cat "$RUN_DIR/foxglove.pid") -- measured ~40% CPU; it must"
  echo "  never sit on the estimator/control data path."
fi

sleep 6
echo
echo "########## verifying the loaded configuration ##########"
grep -a -E '^LOADED_(CONFIG_PATH|CAMERA_IMU_TIME_OFFSET_SEC)' "$OV_LOG" || true
grep -a -E '^LOADED_CAMERA_[01]_INTRINSICS' "$OV_LOG" | cut -c1-150 || true

echo
echo "============================================================"
echo " VIO stack is up."
echo ""
echo " INITIALISATION REQUIREMENT"
echo "   init_dyn_use = false -> STATIC initialisation."
echo "   Keep the camera COMPLETELY STILL until OpenVINS prints"
echo "   'successful initialization'.  Do NOT shake or wave the camera."
echo "   (An earlier version of this script told users to shake the camera for"
echo "    10 s, which directly contradicts static initialisation.)"
echo ""
echo "   tail -f $LOG_DIR/openvins_latest.log | grep -aE 'init|ZUPT'"
echo ""
echo " PX4 vision output is ${SEND_VISION_TO_PX4} by design."
echo "   /odomimu      = estimator output (authoritative)"
echo "   /odomimu_viz  = throttled visualisation ONLY -- never for control or mapping"
echo "============================================================"

echo "$STAMP" > "$RUN_DIR/last_start_stamp"
wait
