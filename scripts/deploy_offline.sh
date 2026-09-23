#!/bin/bash
# deploy_offline.sh -- deploy the audited files from a local staging tarball.
#
# Used when the board cannot reach github (transient HTTP2/connect failures) but
# the operator's machine can.  The staging tarball carries a MANIFEST with the
# exact git commit and per-file SHA256, so the runtime files remain traceable to
# a commit even though the board's own checkout is updated separately.
#
# Usage: deploy_offline.sh <staging_dir> <git_head> [--with-timeshift <value>]
set -o pipefail

STAGE=$1
HEAD_SHA=${2:-unknown}
WITH_TS=""
if [ "${3:-}" = "--with-timeshift" ]; then WITH_TS="$4"; fi

WS=/home/orangepi/kswlt/vio_ws
RUNDIR="$WS/src/open_vins/config/d430"
TS=$(date +%Y%m%dT%H%M%S)
BK=/home/orangepi/kswlt/backups/deploy_$TS
mkdir -p "$BK"

echo "=== offline deploy $TS ==="
echo "  staging : $STAGE"
echo "  git HEAD: $HEAD_SHA"
echo "  backup  : $BK"
echo

backup() { [ -f "$1" ] && cp -a "$1" "$BK/$(echo "$1" | tr '/' '_')" && echo "    backed up $1"; }

deploy() {
  local src=$1 dst=$2
  if [ ! -f "$src" ]; then echo "    MISSING SOURCE $src"; return 1; fi
  mkdir -p "$(dirname "$dst")"
  backup "$dst"
  cp -a "$src" "$dst"
  printf '    %-58s sha256=%s\n' "$(basename "$dst")" "$(sha256sum "$dst" | cut -c1-16)"
}

echo "--- bridge + clock mapper ---"
deploy "$STAGE/vio_bridge_combined.py"  "$WS/vio_bridge/vio_bridge_combined.py"
deploy "$STAGE/imu_clock_mapper.py"     "$WS/vio_bridge/imu_clock_mapper.py"

echo "--- precheck + launchers ---"
mkdir -p "$WS/scripts"
deploy "$STAGE/vio_precheck.py" "$WS/scripts/vio_precheck.py"
deploy "$STAGE/start_vio.sh"            "$WS/start_vio.sh"
deploy "$STAGE/start_vio_systemd.sh"    "$WS/start_vio_systemd.sh"
chmod +x "$WS/start_vio.sh" "$WS/start_vio_systemd.sh" "$WS/scripts/vio_precheck.py"

echo "--- estimator config ---"
deploy "$STAGE/estimator_config.yaml"   "$RUNDIR/estimator_config.yaml"
deploy "$STAGE/kalibr_imu_chain.yaml"   "$RUNDIR/kalibr_imu_chain.yaml"

echo "--- camera-IMU chain ---"
if [ -n "$WITH_TS" ]; then
  echo "  applying verified timeshift = $WITH_TS"
  cp -a "$RUNDIR/kalibr_imucam_chain.yaml" "$BK/kalibr_imucam_chain.yaml.before_ts"
  python3 - "$RUNDIR/kalibr_imucam_chain.yaml" "$WITH_TS" <<'PY'
import sys, re
p, ts = sys.argv[1], sys.argv[2]
lines = open(p).read().split('\n')
out, done, in_cam0 = [], False, False
for ln in lines:
    if re.match(r'^cam0:\s*$', ln):
        in_cam0 = True
    if in_cam0 and not done and 'timeshift_cam_imu' in ln:
        out.append('  timeshift_cam_imu: %s' % ts)
        done = True
        continue
    out.append(ln)
open(p, 'w').write('\n'.join(out))
print('    timeshift set to %s' % ts)
PY
  grep -h timeshift_cam_imu "$RUNDIR/kalibr_imucam_chain.yaml" | sed 's/^/    /'
else
  echo "  NOT touching kalibr_imucam_chain.yaml"
  grep -h timeshift_cam_imu "$RUNDIR/kalibr_imucam_chain.yaml" | sed 's/^/    current: /'
fi

echo "--- systemd ExecStart ---"
if [ -f /etc/systemd/system/vio.service ]; then
  cp -a /etc/systemd/system/vio.service "$BK/vio.service.before"
  python3 - <<PY
import re
p = '/etc/systemd/system/vio.service'
t = open(p).read()
t = re.sub(r'^ExecStart=.*\$', 'ExecStart=$WS/start_vio_systemd.sh', t, flags=re.M)
open(p, 'w').write(t)
PY
  grep -E '^ExecStart' /etc/systemd/system/vio.service | sed 's/^/    /'
  systemctl daemon-reload 2>/dev/null && echo "    daemon-reload ok"
fi

echo "--- retire stale duplicate launchers ---"
for f in /home/orangepi/kswlt/tools/start_vio.sh \
         /home/orangepi/kswlt/tools/start_vio_systemd.sh \
         /home/orangepi/kswlt/vio-improve/start_vio.sh \
         /home/orangepi/kswlt/vio-improve/start_vio_systemd.sh \
         /home/orangepi/kswlt/vio_ws/run_vio.sh ; do
  if [ -f "$f" ]; then
    cp -a "$f" "$BK/$(echo "$f" | tr '/' '_')"
    mv "$f" "$f.DEPRECATED-$TS"
    echo "    retired $f"
  fi
done

cat > "$WS/STARTUP_AUTHORITY.md" <<EOF
# 权威启动入口（部署于 $TS）

    $WS/start_vio.sh            手动启动（唯一权威实现）
    $WS/start_vio_systemd.sh    systemd 包装（仅 flock + 故障锁存，其余全部委托）

两者行为一致是结构性保证，而不是"记得同步"。

来源 commit : $HEAD_SHA
运行配置   : $RUNDIR/
备份       : $BK

任何 \`*.DEPRECATED-$TS\` 都是本次审计退役的旧副本，不得再引用
（其中一个会用 640x480 + imu_bridge.py + vio_to_px4.py）。

一键自检   : python3 $WS/scripts/vio_precheck.py hw|camera|imu $RUNDIR 42
环境约束   : 必须 ROS_LOCALHOST_ONLY=1 ROS_DOMAIN_ID=42，否则发现不到任何节点。
EOF
echo "    wrote $WS/STARTUP_AUTHORITY.md"

echo
echo "--- final runtime hashes ---"
for f in "$RUNDIR/estimator_config.yaml" "$RUNDIR/kalibr_imu_chain.yaml" \
         "$RUNDIR/kalibr_imucam_chain.yaml" \
         "$WS/vio_bridge/vio_bridge_combined.py" "$WS/vio_bridge/imu_clock_mapper.py" \
         "$WS/start_vio.sh" "$WS/start_vio_systemd.sh" "$WS/scripts/vio_precheck.py"; do
  [ -f "$f" ] && printf 'CONFIG_SHA256 %s  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
done
echo
echo "=== offline deploy complete: $TS ==="
