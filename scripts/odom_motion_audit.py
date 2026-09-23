#!/usr/bin/env python3
"""Record /odomimu motion, including in-window excursions and yaw changes.

Usage: ros2 run ... or, after sourcing ROS 2:
  python3 odom_motion_audit.py SECONDS [output.json]

Unlike a first-to-last-only summary, this reports the maximum translation and
yaw excursion from the first sample, so a return-to-origin maneuver is visible.
"""
import json
import math
import sys
import time

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, QoSProfile,
                       ReliabilityPolicy)

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else '/tmp/odom_motion_audit.json'


def percentile(values, q):
    return float(np.percentile(np.asarray(values, dtype=float), q)) if values else None


class Recorder(Node):
    def __init__(self):
        super().__init__('odom_motion_audit')
        qos = QoSProfile(depth=200, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST)
        self.samples = []
        self.create_subscription(Odometry, '/odomimu', self.record, qos)

    def record(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        v = msg.twist.twist.linear
        covariance = (msg.pose.covariance[0], msg.pose.covariance[7],
                      msg.pose.covariance[14])
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        values = (p.x, p.y, p.z, q.x, q.y, q.z, q.w, v.x, v.y, v.z,
                  *covariance)
        self.samples.append((stamp, *values,
                             all(math.isfinite(x) for x in values)))


def summarize(rows):
    if len(rows) < 2:
        return {'samples': len(rows), 'error': 'fewer than 2 odometry samples'}
    a = np.asarray(rows, dtype=float)
    t, pos, quat, vel = a[:, 0], a[:, 1:4], a[:, 4:8], a[:, 8:11]
    covariance = a[:, 11:14]
    finite = a[:, -1] > 0.5
    pos, t, quat, vel, covariance = (pos[finite], t[finite], quat[finite],
                                     vel[finite], covariance[finite])
    if len(pos) < 2:
        return {'samples': len(rows), 'nonfinite': int((~finite).sum()),
                'error': 'fewer than 2 finite samples'}
    steps = np.linalg.norm(np.diff(pos, axis=0), axis=1)
    dts = np.diff(t)
    valid_dt = dts > 0
    step_speed = steps[valid_dt] / dts[valid_dt]
    vnorm = np.linalg.norm(vel, axis=1)
    yaw = np.unwrap(np.arctan2(2 * (quat[:, 3] * quat[:, 2] + quat[:, 0] * quat[:, 1]),
                                1 - 2 * (quat[:, 1]**2 + quat[:, 2]**2)))
    yaw_from_start = yaw - yaw[0]
    excursion = np.linalg.norm(pos - pos[0], axis=1)
    return {
        'samples': int(len(rows)), 'finite_samples': int(finite.sum()),
        'nonfinite': int((~finite).sum()), 'span_s': float(t[-1] - t[0]),
        'path_len_m': float(steps.sum()),
        'displacement_m': float(np.linalg.norm(pos[-1] - pos[0])),
        'max_excursion_from_start_m': float(excursion.max()),
        'max_step_m': float(steps.max()),
        'step_median_m': percentile(steps.tolist(), 50),
        'step_p95_m': percentile(steps.tolist(), 95),
        'step_speed_p95_mps': percentile(step_speed.tolist(), 95),
        'reported_speed_p50_mps': percentile(vnorm.tolist(), 50),
        'reported_speed_p95_mps': percentile(vnorm.tolist(), 95),
        'position_variance_max_p95_m2': percentile(covariance.max(axis=1).tolist(), 95),
        'yaw_excursion_max_deg': float(np.degrees(np.abs(yaw_from_start)).max()),
        'yaw_return_error_deg': float(abs(np.degrees(yaw[-1] - yaw[0]))),
        'n_jumps_10cm': int((steps > 0.10).sum()),
        'n_jumps_50cm': int((steps > 0.50).sum()),
    }


def main():
    rclpy.init()
    node = Recorder()
    start = time.monotonic()
    while time.monotonic() - start < DURATION:
        rclpy.spin_once(node, timeout_sec=0.2)
    result = {'requested_window_s': DURATION, 'odom': summarize(node.samples)}
    node.destroy_node()
    rclpy.shutdown()
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print('written:', OUTPUT)


if __name__ == '__main__':
    main()
