#!/usr/bin/env python3
"""Improved trajectory metrics for replay results.

Fixes the previous version's blind spot: the LASEROFF3 bag ENDS while still
rotating, so there is no "after rotation" still phase. We therefore also report
rotation-phase excursion relative to the last still sample before rotation starts.
"""
import json
import os
import sys
import re
import numpy as np
import rosbag2_py
from rclpy.serialization import deserialize_message
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu

ANSI = re.compile(r'\x1b\[[0-9;]*m')


def rd(uri):
    r = rosbag2_py.SequentialReader()
    r.open(rosbag2_py.StorageOptions(uri=uri, storage_id='sqlite3'),
           rosbag2_py.ConverterOptions(input_serialization_format='cdr',
                                       output_serialization_format='cdr'))
    return r


def read_odom(bagdir):
    rows = []
    r = rd(bagdir)
    while r.has_next():
        topic, data, recv = r.read_next()
        if topic != '/odomimu':
            continue
        m = deserialize_message(data, Odometry)
        t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
        p = m.pose.pose.position
        q = m.pose.pose.orientation
        v = m.twist.twist.linear
        cov = np.asarray(m.pose.covariance, dtype=np.float64)
        rows.append([t, p.x, p.y, p.z, q.x, q.y, q.z, q.w, v.x, v.y, v.z,
                     cov[0], cov[7], cov[14]])
    return np.asarray(rows)


def read_imu(bagdir):
    ts, w, a = [], [], []
    r = rd(bagdir)
    while r.has_next():
        topic, data, recv = r.read_next()
        if topic != '/imu':
            continue
        m = deserialize_message(data, Imu)
        ts.append(m.header.stamp.sec + m.header.stamp.nanosec * 1e-9)
        w.append((m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z))
        a.append((m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z))
    return np.asarray(ts), np.asarray(w), np.asarray(a)


def segments(ts, w, a, binsec=1.0):
    t0 = ts[0]
    bins = ((ts - t0) // binsec).astype(int)
    nb = bins.max() + 1
    wn = np.degrees(np.linalg.norm(w, axis=1))
    an = np.linalg.norm(a, axis=1)
    wr = np.zeros(nb); ad = np.zeros(nb); cnt = np.zeros(nb)
    for b in range(nb):
        m = bins == b
        if m.sum() < 5:
            continue
        cnt[b] = m.sum()
        wr[b] = np.sqrt((wn[m] ** 2).mean())
        ad[b] = an[m].std()
    out = []
    for b in range(nb):
        if cnt[b] < 5:
            k = 'nostream'
        elif wr[b] < 1.0 and ad[b] < 0.15:
            k = 'still'
        elif wr[b] >= 10.0:
            k = 'rotate'
        else:
            k = 'move'
        if out and out[-1][0] == k:
            out[-1][2] = b
        else:
            out.append([k, b, b])
    return [dict(kind=k, t0=float(x), t1=float(y) + 1.0,
                 gyro=float(wr[x:y + 1].max())) for k, x, y in out]


def log_bias(p):
    if not os.path.isfile(p):
        return {}
    ba, bg, init = [], [], False
    for ln in open(p, 'r', encoding='utf-8', errors='replace'):
        s = ANSI.sub('', ln).strip()
        if 'successful initialization' in s:
            init = True
        if not init:
            continue
        m = re.match(r'^bg = (-?[\d.]+),(-?[\d.]+),(-?[\d.]+) \| ba = (-?[\d.]+),(-?[\d.]+),(-?[\d.]+)', s)
        if m:
            g = [float(x) for x in m.groups()]
            bg.append(g[0:3]); ba.append(g[3:6])
    if not ba:
        return {}
    ba = np.asarray(ba); bg = np.asarray(bg)
    return dict(ba_abs_max=float(np.linalg.norm(ba, axis=1).max()),
                bg_abs_max=float(np.linalg.norm(bg, axis=1).max()),
                ba_final=[float(x) for x in ba[-1]],
                n_bias=int(len(ba)))


def main():
    resdir, rawbag, label = sys.argv[1], sys.argv[2], sys.argv[3]
    odom = read_odom(os.path.join(resdir, 'odom'))
    its, iw, ia = read_imu(rawbag)
    segs = segments(its, iw, ia)
    ts = odom[:, 0]; P = odom[:, 1:4]
    base = its[0]
    step = np.linalg.norm(np.diff(P, axis=0), axis=1)

    m = dict(label=label, n=int(len(odom)),
             span=float(ts[-1] - ts[0]),
             path_len_m=float(step.sum()),
             max_jump_m=float(step.max()),
             jumps_gt_10cm=int((step > 0.10).sum()),
             jumps_gt_50cm=int((step > 0.50).sum()),
             final_pos=[float(x) for x in P[-1]],
             closure_m=float(np.linalg.norm(P[-1] - P[0])),
             pos_range=[float(P[:, i].max() - P[:, i].min()) for i in range(3)])
    m.update(log_bias(os.path.join(resdir, 'ov.log')))

    st = [s for s in segs if s['kind'] == 'still' and s['t1'] - s['t0'] >= 3.0]
    if st:
        best = max(st, key=lambda s: s['t1'] - s['t0'])
        sel = (ts >= base + best['t0']) & (ts <= base + best['t1'])
        if sel.sum() > 5:
            exc = np.linalg.norm(P[sel] - P[sel][0], axis=1)
            m['still_seg'] = [best['t0'], best['t1']]
            m['static_drift_m'] = float(exc.max())
            m['static_end_m'] = float(exc[-1])

    rot = [s for s in segs if s['kind'] == 'rotate']
    if rot:
        r0 = base + rot[0]['t0']
        bi = np.where(ts < r0)[0]
        di = np.where(ts >= r0)[0]
        if len(bi) and len(di):
            pb = P[bi[-1]]
            d = np.linalg.norm(P[di] - pb, axis=1)
            m['rot_start_rel_s'] = rot[0]['t0']
            m['rot_peak_excursion_m'] = float(d.max())
            m['rot_final_excursion_m'] = float(d[-1])
            # excursion restricted to only the still->rotate boundary window (first 3 s)
            w3 = di[ts[di] <= r0 + 3.0]
            if len(w3):
                m['rot_first3s_excursion_m'] = float(np.linalg.norm(P[w3] - pb, axis=1).max())
    m['segments'] = segs
    out = os.path.join(resdir, 'metrics2_%s.json' % label)
    with open(out, 'w') as f:
        json.dump(m, f, indent=2, default=float)
    print(json.dumps({k: v for k, v in m.items() if k != 'segments'}, indent=1, default=float))


if __name__ == '__main__':
    main()
