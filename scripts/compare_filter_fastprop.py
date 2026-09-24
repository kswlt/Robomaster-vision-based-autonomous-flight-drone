#!/usr/bin/env python3
"""Record /poseimu (filter EKF) and /odomimu (fastprop) for A/B divergence audit.

Usage (after sourcing ROS 2):
  python3 compare_filter_fastprop.py SECONDS [output.json]

Reports per-topic sample counts, max excursion from first sample, non-finite
counts, and pairwise position delta at nearest timestamps.  A healthy run has
filter and fastprop tracks agreeing within a few cm on a stationary platform;
a 3518 m /odomimu excursion with normal /poseimu is the bug this script exists
to catch.
"""
import json
import math
import sys
import time

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/compare_filter_fastprop.json'


def stamp_of(header):
    return header.stamp.sec + header.stamp.nanosec * 1e-9


def summarize(samples):
    # samples: list of (t, x, y, z, finite)
    if len(samples) < 2:
        return {'samples': len(samples), 'error': 'fewer than 2 samples'}
    a = np.asarray([(s[0], s[1], s[2], s[3], 1.0 if s[4] else 0.0)
                    for s in samples], dtype=float)
    t, pos, finite = a[:, 0], a[:, 1:4], a[:, 4] > 0.5
    pos, t = pos[finite], t[finite]
    if len(pos) < 2:
        return {'samples': int(len(a)), 'nonfinite': int((~finite).sum()),
                'error': 'fewer than 2 finite samples'}
    excursion = np.linalg.norm(pos - pos[0], axis=1)
    steps = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    dts = np.diff(t)
    valid = dts > 0
    step_speed = steps[valid] / dts[valid] if valid.any() else np.array([0.0])
    return {
        'samples': int(len(a)),
        'finite_samples': int(finite.sum()),
        'nonfinite': int((~finite).sum()),
        'span_s': float(t[-1] - t[0]),
        'max_excursion_from_start_m': float(excursion.max()),
        'final_displacement_m': float(np.linalg.norm(pos[-1] - pos[0])),
        'max_step_m': float(steps.max()),
        'step_p95_m': float(np.percentile(steps, 95)),
        'step_speed_p95_mps': float(np.percentile(step_speed, 95)),
        'n_jumps_10cm': int((steps > 0.10).sum()),
        'n_jumps_50cm': int((steps > 0.50).sum()),
    }


def nearest_delta(filter_samples, fast_samples, max_dt=0.05):
    """Max |filter - fastprop| position delta at nearest timestamps."""
    if not filter_samples or not fast_samples:
        return None
    ft = np.asarray([s[0] for s in filter_samples])
    fp = np.asarray([[s[1], s[2], s[3]] for s in filter_samples])
    gt = np.asarray([s[0] for s in fast_samples])
    gp = np.asarray([[s[1], s[2], s[3]] for s in fast_samples])
    # sample every fastprop stamp, find nearest filter stamp
    idx = np.searchsorted(ft, gt)
    idx = np.clip(idx, 1, len(ft) - 1)
    left = idx - 1
    choose_left = np.abs(ft[left] - gt) <= np.abs(ft[idx] - gt)
    near = np.where(choose_left, left, idx)
    dt = np.abs(ft[near] - gt)
    ok = dt <= max_dt
    if not ok.any():
        return {'pairs': 0, 'error': 'no filter sample within %s s' % max_dt}
    delta = np.linalg.norm(fp[near[ok]] - gp[ok], axis=1)
    return {
        'pairs': int(ok.sum()),
        'max_dt_s': float(dt[ok].max()),
        'delta_p50_m': float(np.percentile(delta, 50)),
        'delta_p95_m': float(np.percentile(delta, 95)),
        'delta_max_m': float(delta.max()),
    }


class Recorder(Node):
    def __init__(self):
        super().__init__('compare_filter_fastprop')
        qos = QoSProfile(depth=400, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST)
        self.filter_samples = []
        self.fast_samples = []
        self.create_subscription(Odometry, '/odomimu', self.on_fast, qos)
        self.create_subscription(PoseWithCovarianceStamped, '/poseimu',
                                 self.on_filter, qos)

    def on_fast(self, msg):
        p = msg.pose.pose.position
        self.fast_samples.append((stamp_of(msg.header), p.x, p.y, p.z,
                                  all(math.isfinite(v) for v in (p.x, p.y, p.z))))

    def on_filter(self, msg):
        p = msg.pose.pose.position
        self.filter_samples.append((stamp_of(msg.header), p.x, p.y, p.z,
                                    all(math.isfinite(v) for v in (p.x, p.y, p.z))))


def main():
    rclpy.init()
    node = Recorder()
    start = time.monotonic()
    while time.monotonic() - start < DURATION:
        rclpy.spin_once(node, timeout_sec=0.2)
    result = {
        'requested_window_s': DURATION,
        'filter_poseimu': summarize(node.filter_samples),
        'fastprop_odomimu': summarize(node.fast_samples),
        'pairwise': nearest_delta(node.filter_samples, node.fast_samples),
    }
    node.destroy_node()
    rclpy.shutdown()
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print('written:', OUTPUT)
    # Exit non-zero if fastprop diverged while filter stayed sane (the known bug).
    fe = result['fastprop_odomimu'].get('max_excursion_from_start_m')
    ff = result['filter_poseimu'].get('max_excursion_from_start_m')
    if fe is not None and ff is not None and fe > 10.0 and ff < 1.0:
        print('DIVERGENCE: fastprop excursion %.1f m with filter excursion %.3f m'
              % (fe, ff))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
