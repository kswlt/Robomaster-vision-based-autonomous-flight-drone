#!/usr/bin/env python3
"""Unique bag directory, configuration snapshots and immutable content hashes."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time

TOPICS = ['/imu', '/camera/camera/infra1/image_rect_raw',
          '/camera/camera/infra2/image_rect_raw', '/camera/camera/infra1/camera_info',
          '/camera/camera/infra2/camera_info', '/odomimu', '/poseimu', '/tf', '/tf_static']


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('motion', choices=['STATIC', 'ROTATION_ONLY', 'TRANSLATION', 'RECTANGLE', 'TIMING_ONLY', 'IMU_NOISE'])
    p.add_argument('seconds', type=float)
    p.add_argument('notes', nargs='?', default='')
    p.add_argument('--root', default='/home/orangepi/vio_data')
    a = p.parse_args()
    if a.seconds <= 0 or (a.motion == 'STATIC' and a.seconds < 120) or (a.motion == 'IMU_NOISE' and a.seconds < 300):
        p.error('duration must be positive; STATIC >=120s, IMU_NOISE >=300s')
    devices = [d for d in Path('/sys/bus/usb/devices').glob('*')
               if (d / 'idProduct').exists() and (d / 'idVendor').read_text().strip() == '8086'
               and (d / 'idProduct').read_text().strip() == '0ad4']
    devices = [d for d in devices if (d / 'serial').read_text().strip() == '938422073656']
    if len(devices) != 1 or float((devices[0] / 'speed').read_text()) < 5000:
        raise SystemExit('INVALID: expected D430 serial at USB3 >=5000M')
    run = Path(a.root) / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ_') + a.motion)
    run.mkdir(parents=True, exist_ok=False)
    cfg = Path('/home/orangepi/vio_ws/src/open_vins/config/d430')
    for name in ('estimator_config.yaml', 'kalibr_imucam_chain.yaml', 'kalibr_imu_chain.yaml'):
        (run / name).write_bytes((cfg / name).read_bytes())
    qos = run / 'qos.yaml'
    qos.write_text('/tf_static:\n  durability: transient_local\n  reliability: reliable\n  history: keep_last\n  depth: 100\n')
    manifest = dict(motion=a.motion, requested_seconds=a.seconds, notes=a.notes,
                    status='RECORDING', ground_truth='NO EXTERNAL GROUND TRUTH',
                    validation='RELATIVE VALIDATION', topics=TOPICS,
                    usb_speed_mbps=float((devices[0] / 'speed').read_text()),
                    serial='938422073656', start_unix=time.time())
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(f'RECORDING {run}', flush=True)
    with (run / 'recorder.log').open('w') as log:
        proc = subprocess.Popen(['ros2', 'bag', 'record', '-s', 'sqlite3', '-o', str(run / 'bag'),
                                 '--qos-profile-overrides-path', str(qos), *TOPICS], stdout=log, stderr=log)
        try:
            proc.wait(timeout=a.seconds)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    manifest.update(end_unix=time.time(), recorder_exit=proc.returncode,
                    status='RECORDED_UNVALIDATED' if (run / 'bag/metadata.yaml').exists() else 'INVALID')
    hashes = {}
    for f in sorted(run.rglob('*')):
        if f.is_file() and f.name != 'manifest.json':
            h = hashlib.sha256()
            with f.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            hashes[str(f.relative_to(run))] = h.hexdigest()
    manifest['sha256'] = hashes
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    if manifest['status'] == 'INVALID':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
