#!/usr/bin/env python3
"""Replay all clock-mapping strategies over the REAL PX4 trace.

The bridge's diagnostic CSV records both the raw sensor_time and the arrival
time, so the mapping can be re-run offline on genuine hardware data -- including
the real +0.45 s PX4 time_usec step that was observed.  This is the strongest
available validation short of a live camera run.

Reports, per strategy: monotonicity, dt distribution, implausible-dt count,
repairs, and the resulting time-axis rate error against arrival time.
"""
import csv
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (_HERE, os.path.dirname(_HERE)):
    if os.path.isfile(os.path.join(_c, 'imu_clock_mapper.py')):
        sys.path.insert(0, _c)
        break
from imu_clock_mapper import ImuClockMapper  # noqa: E402


def quant(v, p):
    if not v:
        return float('nan')
    s = sorted(v)
    return s[min(len(s) - 1, max(0, int(p * (len(s) - 1))))]


def load(path):
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            try:
                out.append((float(row['sensor_time']), float(row['arrival_time'])))
            except (ValueError, KeyError):
                continue
    return out


def run(mode, samples):
    m = ImuClockMapper(mode=mode, nominal_rate=200.0)
    prev = None
    viol = 0
    dts, stamps, arrivals = [], [], []
    for st, at in samples:
        s, d = m.update(st, at)
        if prev is not None and s <= prev:
            viol += 1
        prev = s
        stamps.append(s)
        arrivals.append(at)
        if d['final_dt'] is not None:
            dts.append(d['final_dt'])
    return m, dts, stamps, arrivals, viol


def main():
    path = sys.argv[1]
    samples = load(path)
    print('real trace: %s  (%d packets, sensor span %.1f s)'
          % (os.path.basename(path), len(samples), samples[-1][0] - samples[0][0]))
    print()
    print('%-9s %7s %11s %11s %11s %10s %9s %9s' % (
        'mode', 'viol', 'dt_p50', 'dt_p99', 'dt_max', 'small_dt', 'repairs', 'axis_ppm'))
    print('-' * 84)
    best = None
    for mode in ImuClockMapper.MODES:
        m, dts, stamps, arrivals, viol = run(mode, samples)
        sm = m.summary()
        small = sum(1 for x in dts if x < 1e-4)
        axis = ((stamps[-1] - stamps[0]) / (arrivals[-1] - arrivals[0]) - 1.0) * 1e6 \
            if arrivals[-1] > arrivals[0] else 0.0
        print('%-9s %7d %11.6f %11.6f %11.6f %10d %9d %9.1f' % (
            mode, viol, quant(dts, .5), quant(dts, .99), max(dts), small,
            sm['n_repairs'], axis))
        if mode == 'slow':
            best = (sm, dts, viol, axis, small)
    print()
    if best:
        sm, dts, viol, axis, small = best
        print('slow detail:')
        print('  clock_offset slope  : %+.3e s/s (%+.1f ppm)'
              % (sm['offset_slope_s_per_s'] or 0.0, (sm['offset_slope_s_per_s'] or 0.0) * 1e6))
        print('  scale_ppm final     : %+.1f (slope updates %d)'
              % (sm['scale_ppm'], sm['slope_updates']))
        print('  clock_resets        : %d   reanchor_backwards: %d   n_resets: %d'
              % (sm['n_clock_reset'], sm['n_reanchor_backwards'], sm['n_resets']))
        print('  gated / gate_forced : %d / %d' % (sm['n_gated'], sm['n_gate_forced']))
        print('  dt < 100us          : %d  (should be 0)' % small)
        print('  monotonic           : %s' % (viol == 0))
        print()
        print('  dt histogram:')
        edges = [0.003, 0.005, 0.006, 0.008, 0.011, 0.015, 0.05, 0.5]
        labels = ['<3ms', '3-5', '5-6', '6-8', '8-11', '11-15', '15-50', '50-500', '>500ms']
        c = [0] * (len(edges) + 1)
        for x in dts:
            i = 0
            while i < len(edges) and x > edges[i]:
                i += 1
            c[i] += 1
        for lab, n in zip(labels, c):
            if n:
                print('     %-9s %6d %5.1f%%  %s' % (lab, n, 100.0 * n / len(dts),
                                                     '#' * max(1, int(50.0 * n / len(dts)))))


if __name__ == '__main__':
    main()
