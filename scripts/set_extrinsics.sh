#!/bin/bash
# ============================================================================
#  双目外参切换（只动 cam1 相对 cam0 的相对位姿，其它一律不动）
#
#    rect50     使用 RealSense 整流后的真实几何：R=I，基线 50.137518 mm
#               —— 与 bag 里 CameraInfo / D430 出厂基线一致（推荐）
#    baseline46 使用 git 里原来的 cam1（基线只 46.88 mm，短 6.3%）
#               —— 保留它是为了做实机 A/B
#    show       只打印当前生效的外参与反推基线，不改任何东西
#
#  用法: scripts/set_extrinsics.sh {rect50|baseline46|show}
# ============================================================================
set -o pipefail

C=${VIO_CFG_DIR:-/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430}
ACT="$C/kalibr_imucam_chain.yaml"
RECT="$C/kalibr_imucam_chain.rect50.yaml"
BASE="$C/kalibr_imucam_chain.baseline46.yaml"
MODE=${1:-show}

report () {
  python3 - "$ACT" <<'PY'
import re
import sys
import numpy as np

p = sys.argv[1]
txt = open(p).read()
T = {}
for cam in ('cam0', 'cam1'):
    m = re.search(r'^%s:\s*$(.*?)(?=^cam\d:|\Z)' % cam, txt, re.S | re.M)
    tm = re.search(r'T_imu_cam:\s*\n((?:\s*-\s*\[[^\]]*\]\s*\n){4})', m.group(1))
    rows = re.findall(r'\[([^\]]*)\]', tm.group(1))
    T[cam] = np.array([[float(x) for x in r.split(',')] for r in rows])
ts = re.search(r'timeshift_cam_imu:\s*([-\d.]+)', txt).group(1)
A = np.linalg.inv(T['cam1']) @ T['cam0']          # 估计器实际使用的 T_cam1_cam0
t, R = A[:3, 3], A[:3, :3]
ang = np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
print('  文件          = %s' % p)
print('  timeshift     = %s' % ts)
print('  T_cam1_cam0 t = [%.6f, %.6f, %.6f] m' % tuple(t))
print('  实际基线       = %.6f mm   (真实值 50.137518 mm)' % (np.linalg.norm(t) * 1000))
print('  相对旋转       = %.4f deg   (整流后应为 0)' % ang)
print('  基线误差       = %+.2f%%'
      % (100.0 * (np.linalg.norm(t) * 1000 - 50.137518) / 50.137518))
PY
}

case "$MODE" in
  show)
    if [ ! -f "$ACT" ]; then echo "找不到 $ACT"; exit 1; fi
    echo "=== 当前生效的双目外参 ==="
    report
    printf '  sha256        = %s\n' "$(sha256sum "$ACT" | cut -d' ' -f1)"
    ;;
  rect50|baseline46)
    [ -f "$RECT" ] || { echo "缺少 $RECT"; exit 1; }
    [ -f "$BASE" ] || { echo "缺少 $BASE"; exit 1; }
    if pgrep -f 'run_subscribe_msckf' >/dev/null 2>&1; then
      echo "估计器正在运行：先停掉再切外参（bash start_vio.sh 的 Ctrl-C，或 bash /tmp/live_validate.sh stop）"
      exit 1
    fi
    SRC=$RECT; [ "$MODE" = "baseline46" ] && SRC=$BASE
    STAMP=$(date +%Y%m%dT%H%M%S)
    mkdir -p "$HOME/kswlt/backups"
    cp -a "$ACT" "$HOME/kswlt/backups/kalibr_imucam_chain.before_${MODE}_$STAMP.yaml" 2>/dev/null
    cp -a "$SRC" "$ACT"
    echo "=== 已切到 $MODE ==="
    report
    printf '  sha256        = %s\n' "$(sha256sum "$ACT" | cut -d' ' -f1)"
    echo "  备份          = $HOME/kswlt/backups/kalibr_imucam_chain.before_${MODE}_$STAMP.yaml"
    ;;
  *)
    echo "用法: $0 {rect50|baseline46|show}"
    exit 2
    ;;
esac
