#!/usr/bin/env python3
"""Analyze every sensor header stamp in a ROS2 bag, not callback arrival offsets.

Nearest IMU distance measures sampling alignment, NOT temporal calibration.
All reported intervals are seconds; FPS excludes nonpositive intervals.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np

LEFT = '/camera/camera/infra1/image_rect_raw'
RIGHT = '/camera/camera/infra2/image_rect_raw'


def distribution(values):
    x = np.asarray(values, dtype=float)
    if not x.size:
        return dict(count=0, mean=None, median=None, std=None, min=None, max=None, p95=None, p99=None)
    return dict(count=int(x.size), mean=float(x.mean()), median=float(np.median(x)),
                std=float(x.std()), min=float(x.min()), max=float(x.max()),
                p95=float(np.percentile(x, 95)), p99=float(np.percentile(x, 99)))


def nearest_distances(query, target):
    if not len(target):
        return np.array([])
    target = np.sort(np.asarray(target, dtype=np.int64))
    query = np.asarray(query, dtype=np.int64)
    i = np.searchsorted(target, query)
    return np.minimum(np.abs(query-target[np.clip(i, 0, len(target)-1)]),
                      np.abs(query-target[np.clip(i-1, 0, len(target)-1)])) * 1e-9


def stream_stats(stamps):
    stamps = np.asarray(stamps, dtype=np.int64)
    dt = np.diff(stamps) * 1e-9
    positive = dt[dt > 0]
    return dict(frame_count=len(stamps), duration_sec=float((stamps[-1]-stamps[0])*1e-9) if len(stamps)>1 else 0,
                largest_gaps=[dict(start_ns=int(stamps[i]),end_ns=int(stamps[i+1]),
                                   elapsed_sec=float((stamps[i]-stamps[0])*1e-9),gap_sec=float(dt[i]))
                              for i in np.argsort(dt)[-5:][::-1]],
                rate_hz=float((len(stamps)-1)/((stamps[-1]-stamps[0])*1e-9)) if len(stamps)>1 and stamps[-1]>stamps[0] else None,
                dt_sec=distribution(dt), fps=distribution(1/positive),
                negative_timestamp_count=int((dt<0).sum()), duplicate_timestamp_count=int((dt==0).sum()))


def summarize(left, right, imu, tolerance_sec=0.001):
    # Monotonic one-to-one pairing: never reuse an image for two stereo pairs.
    l, r = sorted(left), sorted(right)
    i = j = 0
    skew = []
    tolerance_ns = round(tolerance_sec*1e9)
    while i < len(l) and j < len(r):
        delta = l[i] - r[j]
        if abs(delta) <= tolerance_ns:
            skew.append(delta*1e-9)
            i += 1
            j += 1
        elif delta < 0:
            i += 1
        else:
            j += 1
    return dict(camera_left=stream_stats(left), camera_right=stream_stats(right), imu=stream_stats(imu),
                stereo=dict(pair_tolerance_sec=tolerance_sec, paired_count=len(skew),
                            unmatched_left_count=len(left)-len(skew), unmatched_right_count=len(right)-len(skew),
                            frame_pairing_mismatch_count=len(left)+len(right)-2*len(skew),
                            paired_left_minus_right_sec=distribution(skew),
                            paired_absolute_skew_sec=distribution(np.abs(skew)),
                            all_left_nearest_right_sec=distribution(nearest_distances(left,right))),
                camera_nearest_imu_sec=dict(left=distribution(nearest_distances(left,imu)),
                                           right=distribution(nearest_distances(right,imu))),
                interpretation='Nearest sampling distance is NOT camera-IMU time calibration; paired skew is tolerance-censored. Inspect unmatched counts and all-left nearest-right distribution.')


def read_bag(path, topics=None):
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    import yaml
    metadata = yaml.safe_load((Path(path)/'metadata.yaml').read_text())['rosbag2_bagfile_information']
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(path), storage_id=metadata['storage_identifier']),
                rosbag2_py.ConverterOptions('', ''))
    types = {x.name: get_message(x.type) for x in reader.get_all_topics_and_types()}
    if topics:
        reader.set_filter(rosbag2_py.StorageFilter(topics=list(topics)))
    while reader.has_next():
        topic, data, arrival = reader.read_next()
        yield topic, deserialize_message(data, types[topic]), arrival


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('bag')
    p.add_argument('--output', default='results/vio_validation')
    p.add_argument('--pair-tolerance-ms', type=float, default=1)
    a = p.parse_args()
    stamps = {LEFT: [], RIGHT: [], '/imu': []}
    receipt = {k: [] for k in stamps}
    for topic, msg, arrival in read_bag(a.bag, stamps):
        t = msg.header.stamp.sec*10**9 + msg.header.stamp.nanosec
        stamps[topic].append(t)
        receipt[topic].append((arrival-t)*1e-9)
    result = summarize(stamps[LEFT], stamps[RIGHT], stamps['/imu'], a.pair_tolerance_ms/1000)
    result['bag'] = str(Path(a.bag).resolve())
    result['bag_receipt_minus_header_sec'] = {k: distribution(v) for k,v in receipt.items()}
    result['core_topics_present'] = all(len(v)>1 for v in stamps.values())
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    (out/'timing_summary.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    with (out/'timing_summary.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['metric','value'])
        def flatten(d, prefix=''):
            for k,v in d.items():
                name = f'{prefix}.{k}' if prefix else k
                if isinstance(v,dict):
                    flatten(v,name)
                else:
                    writer.writerow([name,v])
        flatten(result)
    print(json.dumps(result, indent=2))
    if not result['core_topics_present']:
        raise SystemExit('INVALID: missing core streams')


if __name__ == '__main__':
    main()
