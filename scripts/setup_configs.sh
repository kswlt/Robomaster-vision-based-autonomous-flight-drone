#!/bin/bash
# setup_configs.sh -- build clean, single-source config dirs for replay A/B
# The RUNNING config dir is the authoritative one (git HEAD has the stale +0.001256).
set -eu
RUN=/home/orangepi/kswlt/vio_ws/src/open_vins/config/d430
W=/home/orangepi/kswlt/vio_replay
mkdir -p $W/configs $W/logs $W/out

echo "=== base config from RUNNING dir (has timeshift -0.010) ==="
rm -rf $W/configs/base
mkdir -p $W/configs/base
cp $RUN/estimator_config.yaml   $W/configs/base/
cp $RUN/kalibr_imu_chain.yaml   $W/configs/base/
cp $RUN/kalibr_imucam_chain.yaml $W/configs/base/
grep -n 'timeshift_cam_imu' $W/configs/base/kalibr_imucam_chain.yaml
sha256sum $W/configs/base/*

echo
echo "=== make a timeshift variant: mkcfg.sh <name> <timeshift_sec> ==="
cat > $W/mkcfg.sh <<'EOS'
#!/bin/bash
# usage: mkcfg.sh <name> <timeshift_sec> [base]
set -eu
W=/home/orangepi/kswlt/vio_replay
NAME=$1; TS=$2; BASE=${3:-$W/configs/base}
D=$W/configs/$NAME
rm -rf $D; mkdir -p $D
cp $BASE/estimator_config.yaml $BASE/kalibr_imu_chain.yaml $BASE/kalibr_imucam_chain.yaml $D/
if [ "$TS" != "KEEP" ]; then
  python3 - "$D/kalibr_imucam_chain.yaml" "$TS" <<'PY'
import sys, re
p, ts = sys.argv[1], sys.argv[2]
lines = open(p).read().split('\n')
out, done = [], False
for ln in lines:
    if 'timeshift_cam_imu' in ln and not done:
        out.append('  timeshift_cam_imu: %s' % ts)
        done = True
    else:
        out.append(ln)
open(p, 'w').write('\n'.join(out))
print('  set timeshift_cam_imu = %s in %s' % (ts, p))
PY
fi
grep -n 'timeshift_cam_imu' $D/kalibr_imucam_chain.yaml
EOS
chmod +x $W/mkcfg.sh
echo "OK"
