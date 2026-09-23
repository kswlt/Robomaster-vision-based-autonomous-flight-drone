#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a config variant for single-variable A/B replay.

    mksweep.py <base_config_dir> <dest_config_dir> key=value [key=value ...]

Supported keys and the file they are written to:
    timeshift_cam_imu        kalibr_imucam_chain.yaml  (cam0)
    zupt_chi2_multipler      estimator_config.yaml
    zupt_max_disparity       estimator_config.yaml
    zupt_max_velocity        estimator_config.yaml
    zupt_noise_multiplier    estimator_config.yaml
    try_zupt                 estimator_config.yaml
    init_max_disparity       estimator_config.yaml
    init_imu_thresh          estimator_config.yaml
    init_dyn_use             estimator_config.yaml
    update_rate              kalibr_imu_chain.yaml
    max_clones               estimator_config.yaml
    num_pts                  estimator_config.yaml
    fast_threshold           estimator_config.yaml
    up_msckf_chi2_multipler  estimator_config.yaml

Only the requested keys are rewritten; every other byte of the config is
preserved, so an A/B really does change one variable at a time.
"""
import os
import re
import shutil
import sys

EST = 'estimator_config.yaml'
CAM = 'kalibr_imucam_chain.yaml'
IMU = 'kalibr_imu_chain.yaml'

EST_KEYS = {
    'zupt_chi2_multipler', 'zupt_max_disparity', 'zupt_max_velocity',
    'zupt_noise_multiplier', 'try_zupt', 'init_max_disparity',
    'init_imu_thresh', 'init_dyn_use', 'max_clones', 'num_pts',
    'fast_threshold', 'up_msckf_chi2_multipler', 'track_frequency',
    'min_px_dist', 'fast_threshold', 'downsample_cameras',
}
IMU_KEYS = {'update_rate'}


def set_scalar(path, key, value, section=None):
    """Replace `key: <anything>` with `key: <value>` (first match after section)."""
    lines = open(path, 'r').read().split('\n')
    out = []
    done = False
    in_section = section is None
    for ln in lines:
        if section is not None and re.match(r'^%s:\s*$' % re.escape(section), ln):
            in_section = True
            out.append(ln)
            continue
        if in_section and not done and re.match(r'^\s*%s\s*:' % re.escape(key), ln):
            indent = re.match(r'^(\s*)', ln).group(1)
            out.append('%s%s: %s' % (indent, key, value))
            done = True
            continue
        out.append(ln)
    if not done:
        raise SystemExit('key %r not found in %s' % (key, path))
    open(path, 'w').write('\n'.join(out))


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    base, dest = sys.argv[1], sys.argv[2]
    pairs = []
    for a in sys.argv[3:]:
        if '=' not in a:
            raise SystemExit('expected key=value, got %r' % a)
        k, v = a.split('=', 1)
        pairs.append((k.strip(), v.strip()))

    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    for n in (EST, CAM, IMU):
        src = os.path.join(base, n)
        if not os.path.isfile(src):
            raise SystemExit('missing %s in %s' % (n, base))
        shutil.copy2(src, os.path.join(dest, n))

    for k, v in pairs:
        if k == 'timeshift_cam_imu':
            set_scalar(os.path.join(dest, CAM), k, v, section='cam0')
        elif k in EST_KEYS:
            set_scalar(os.path.join(dest, EST), k, v)
        elif k in IMU_KEYS:
            set_scalar(os.path.join(dest, IMU), k, v)
        else:
            raise SystemExit('unsupported key %r' % k)
        print('  set %s = %s' % (k, v))

    for n in (EST, CAM, IMU):
        p = os.path.join(dest, n)
        print('  %s  sha256(short)=%s' % (n, __import__('hashlib').sha256(
            open(p, 'rb').read()).hexdigest()[:16]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
