#!/usr/bin/env python3
"""Time-line audit of a raw VIO bag.

Extracts, for every message:
  * the ROS recording timestamp (rosbag2 `messages.timestamp`, = arrival time in the
    host clock domain)
  * the message's OWN header.stamp (what the publisher stamped it with)

For /imu this lets us separate the two layers the task cares about:
  layer 1 = PX4 sensor time -> ROS stamp   (bridge clock mapping)
  layer 2 = camera exposure vs IMU sample  (OpenVINS timeshift)

Also segments the recording into still / rotating / translating phases using the
raw inertial signals, so later metrics can be tied to actual motion.
"""
import json
import os
import sys
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image, Imu


def pct(a, p):
    return float(np.percentile(a, p)) if len(a) else float('nan')


def stat(a, name, out):
    a = np.asarray(a, dtype=np.float64)
    if a.size == 0:
        out[name] = None
        return
    out[name] = dict(n=int(a.size), mean=float(a.mean()), std=float(a.std()),
                     min=float(a.min()), p50=pct(a, 50), p95=pct(a, 95),
                     p99=pct(a, 99), max=float(a.max()))


def main():
    bag = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(bag.rstrip('/'))
    outdir = sys.argv[3] if len(sys.argv) > 3 else '/tmp'
    print('### BAG %s (%s)' % (label, bag))

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag, storage_id='sqlite3'),
                rosbag2_py.ConverterOptions(input_serialization_format='cdr',
                                            output_serialization_format='cdr'))

    imu_stamp, imu_recv, imu_w, imu_a = [], [], [], []
    cam = {}
    ts_lo, ts_hi = None, None
    n = 0
    while reader.has_next():
        topic, data, recv = reader.read_next()
        n += 1
        if ts_lo is None:
            ts_lo = recv
        ts_hi = recv
        if topic == '/imu':
            m = deserialize_message(data, Imu)
            s = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
            imu_stamp.append(s)
            imu_recv.append(recv * 1e-9)
            imu_w.append((m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z))
            imu_a.append((m.linear_acceleration.x, m.linear_acceleration.y,
                          m.linear_acceleration.z))
        elif topic.endswith('image_rect_raw'):
            key = topic.split('/')[-2]
            m = deserialize_message(data, Image)
            s = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
            cam.setdefault(key, []).append((s, recv * 1e-9))

    res = dict(label=label, bag=bag, total_messages=n)
    res['bag_span_recv_sec'] = (ts_hi - ts_lo) * 1e-9 if ts_lo else None
    print('  total messages      = %d' % n)
    print('  bag span (recv)     = %.3f s' % res['bag_span_recv_sec'])

    # ---------------- IMU ----------------
    imu_stamp = np.asarray(imu_stamp)
    imu_recv = np.asarray(imu_recv)
    imu_w = np.asarray(imu_w)
    imu_a = np.asarray(imu_a)
    print('\n--- /imu ---')
    print('  count = %d  stamp span = %.3f s' % (len(imu_stamp), imu_stamp[-1] - imu_stamp[0]))
    print('  stamp domain (unix?) : first=%.6f last=%.6f' % (imu_stamp[0], imu_stamp[-1]))
    print('  recv  domain         : first=%.6f last=%.6f' % (imu_recv[0], imu_recv[-1]))
    res['imu_count'] = int(len(imu_stamp))
    res['imu_stamp_first'] = float(imu_stamp[0])
    res['imu_recv_first'] = float(imu_recv[0])

    dt = np.diff(imu_stamp)
    d = {}
    stat(dt, 'imu_dt', d)
    stat(1.0 / dt[dt > 0], 'imu_rate', d)
    # arrival offset: recv - stamp  (this is what the bridge tries to cancel)
    ao = imu_recv - imu_stamp
    stat(ao, 'imu_arrival_offset', d)
    stat(np.diff(ao), 'imu_arrival_offset_stepdiff', d)
    res.update(d)
    print('  dt          : mean=%.6f p50=%.6f p95=%.6f p99=%.6f min=%.6f max=%.6f' % (
        d['imu_dt']['mean'], d['imu_dt']['p50'], d['imu_dt']['p95'],
        d['imu_dt']['p99'], d['imu_dt']['min'], d['imu_dt']['max']))
    print('  rate(Hz)    : mean=%.2f p50=%.2f p95=%.2f' % (
        d['imu_rate']['mean'], d['imu_rate']['p50'], d['imu_rate']['p95']))
    print('  arrival_off : mean=%.6f std=%.6f min=%.6f p50=%.6f p95=%.6f max=%.6f' % (
        d['imu_arrival_offset']['mean'], d['imu_arrival_offset']['std'],
        d['imu_arrival_offset']['min'], d['imu_arrival_offset']['p50'],
        d['imu_arrival_offset']['p95'], d['imu_arrival_offset']['max']))
    gaps = np.where(dt > 0.02)[0]
    res['imu_gaps_gt20ms'] = int(len(gaps))
    print('  gaps > 20ms : %d' % len(gaps))
    for i in gaps[:10]:
        print('      at t=+%.3f s  dt=%.4f s' % (imu_stamp[i] - imu_stamp[0], dt[i]))
    # negative / duplicated stamps
    res['imu_nonpositive_dt'] = int((dt <= 0).sum())
    print('  dt <= 0     : %d' % res['imu_nonpositive_dt'])

    wn = np.linalg.norm(imu_w, axis=1)
    an = np.linalg.norm(imu_a, axis=1)
    print('  |gyro| deg/s: mean=%.3f p50=%.3f p95=%.3f max=%.3f' % (
        np.degrees(wn).mean(), np.degrees(np.percentile(wn, 50)),
        np.degrees(np.percentile(wn, 95)), np.degrees(wn.max())))
    print('  |accel| m/s2: mean=%.3f p50=%.3f p95=%.3f max=%.3f' % (
        an.mean(), np.percentile(an, 50), np.percentile(an, 95), an.max()))

    # ---------------- CAMERAS ----------------
    for key in sorted(cam):
        arr = np.asarray(cam[key])
        st = arr[:, 0]
        rc = arr[:, 1]
        print('\n--- %s ---' % key)
        print('  count = %d  stamp span = %.3f s' % (len(st), st[-1] - st[0]))
        print('  stamp domain : first=%.6f last=%.6f' % (st[0], st[-1]))
        cdt = np.diff(st)
        cd = {}
        stat(cdt, 'cam_dt', cd)
        stat(1.0 / cdt[cdt > 0], 'cam_rate', cd)
        stat(rc - st, 'cam_arrival_offset', cd)
        res['cam_' + key] = cd
        print('  dt   : mean=%.6f p50=%.6f p95=%.6f max=%.6f' % (
            cd['cam_dt']['mean'], cd['cam_dt']['p50'], cd['cam_dt']['p95'],
            cd['cam_dt']['max']))
        print('  rate : mean=%.3f p50=%.3f' % (cd['cam_rate']['mean'], cd['cam_rate']['p50']))
        print('  arrival_off : mean=%.6f std=%.6f p95=%.6f max=%.6f' % (
            cd['cam_arrival_offset']['mean'], cd['cam_arrival_offset']['std'],
            cd['cam_arrival_offset']['p95'], cd['cam_arrival_offset']['max']))
        cgaps = np.where(cdt > 0.06)[0]
        res['cam_%s_gaps_gt60ms' % key] = int(len(cgaps))
        print('  gaps > 60ms : %d' % len(cgaps))

    # ---------------- CROSS-DOMAIN CHECK ----------------
    if len(imu_stamp) and cam:
        print('\n--- CAMERA vs IMU TIMESTAMP DOMAIN CROSS-CHECK ---')
        for key in sorted(cam):
            st = np.asarray(cam[key])[:, 0]
            k = min(len(st), 400)
            idx = np.linspace(0, len(st) - 1, k).astype(int)
            diffs = []
            for i in idx:
                j = np.searchsorted(imu_stamp, st[i])
                j = min(max(j, 0), len(imu_stamp) - 1)
                alts = [imu_stamp[j]]
                if j > 0:
                    alts.append(imu_stamp[j - 1])
                if j + 1 < len(imu_stamp):
                    alts.append(imu_stamp[j + 1])
                diffs.append(st[i] - min(alts, key=lambda v: abs(v - st[i])))
            diffs = np.asarray(diffs)
            res['cam_%s_minus_nearest_imu' % key] = dict(
                mean=float(diffs.mean()), std=float(diffs.std()),
                min=float(diffs.min()), max=float(diffs.max()))
            print('  %s - nearest /imu stamp: mean=%+.6f std=%.6f min=%+.6f max=%+.6f' % (
                key, diffs.mean(), diffs.std(), diffs.min(), diffs.max()))

    # ---------------- MOTION SEGMENTATION ----------------
    print('\n--- MOTION SEGMENTATION (from raw IMU, 1 s bins) ---')
    if len(imu_stamp) > 100:
        t0 = imu_stamp[0]
        bins = ((imu_stamp - t0) // 1.0).astype(int)
        nb = bins.max() + 1
        gyro_rms = np.zeros(nb)
        acc_dev = np.zeros(nb)
        cnt = np.zeros(nb)
        gmean = np.median(an)
        for b in range(nb):
            m = bins == b
            if m.sum() < 5:
                continue
            cnt[b] = m.sum()
            gyro_rms[b] = np.degrees(np.sqrt((wn[m] ** 2).mean()))
            acc_dev[b] = an[m].std()
        segs = []
        for b in range(nb):
            if cnt[b] < 5:
                kind = 'nostream'
            elif gyro_rms[b] < 1.0 and acc_dev[b] < 0.15:
                kind = 'still'
            elif gyro_rms[b] >= 10.0:
                kind = 'rotate'
            else:
                kind = 'move'
            if segs and segs[-1][0] == kind:
                segs[-1][2] = b
            else:
                segs.append([kind, b, b])
        for kind, b0, b1 in segs:
            print('  %-9s t=%6.1f .. %6.1f s  (%d s)  gyro_rms_max=%.1f deg/s' % (
                kind, b0, b1 + 1, b1 + 1 - b0,
                gyro_rms[b0:b1 + 1].max() if b1 >= b0 else 0))
        res['segments'] = [dict(kind=k, t0=int(a), t1=int(b) + 1) for k, a, b in segs]

    path = os.path.join(outdir, 'time_audit_%s.json' % label)
    with open(path, 'w') as f:
        json.dump(res, f, indent=2, default=float)
    print('\nWROTE %s' % path)


if __name__ == '__main__':
    main()
