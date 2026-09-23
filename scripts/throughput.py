#!/usr/bin/env python3
"""Compare estimator throughput: offline replay vs the live run.

Reads one or more OpenVINS logs and reports how many camera frames were actually
processed, the per-frame CPU cost, and the implied processing rate.  This is the
measurement behind the 'offline is fine, live drifts' observation: the live run
was processing only ~15.5 Hz of a 30 Hz stream because a single frame cost more
than the frame period.
"""
import re
import sys
import glob

ANSI = re.compile(r'\x1b\[[0-9;]*m')
RET = re.compile(r'^\[TIME\]: ([\d.]+) seconds total \(([\d.]+) hz, ([\d.]+) ms behind\)')


def analyse(path, label):
    frames = 0
    tot = []
    behind = []
    init = 0
    try:
        fh = open(path, 'r', encoding='utf-8', errors='replace')
    except Exception:
        return None
    for ln in fh:
        s = ANSI.sub('', ln).strip()
        if s.startswith('q_GtoI'):
            frames += 1
        if 'successful initialization' in s:
            init += 1
        m = RET.match(s)
        if m:
            tot.append(float(m.group(1)))
            behind.append(float(m.group(3)))
    if not tot:
        return None
    v = sorted(tot)
    n = len(v)
    q = lambda t: v[min(n - 1, max(0, int(t * (n - 1))))]
    mean = sum(v) / n
    over = sum(1 for x in v if x > 1.0 / 30.0)
    return dict(label=label, path=path, time_reports=n, qgt_frames=frames,
                init=init, cpu_mean=mean, cpu_p50=q(.5), cpu_p95=q(.95),
                cpu_max=v[-1], implied_hz=(1.0 / mean if mean else 0.0),
                over_budget=over, over_pct=100.0 * over / n,
                wall_span_s=n * mean)


def main():
    paths = sys.argv[1:]
    if not paths:
        paths = sorted(glob.glob('/tmp/vio/openvins_*.log'))
    rows = []
    for p in paths:
        r = analyse(p, p.split('/')[-1])
        if r:
            rows.append(r)
    print('%-34s %9s %8s %9s %9s %9s %9s %7s' % (
        'log', 'frames', 'init', 'cpu_mean', 'cpu_p50', 'cpu_p95', 'impliedHz', 'over%'))
    print('-' * 100)
    for r in rows:
        print('%-34s %9d %8d %9.4f %9.4f %9.4f %9.2f %6.1f%%' % (
            r['label'][:34], r['qgt_frames'], r['init'], r['cpu_mean'],
            r['cpu_p50'], r['cpu_p95'], r['implied_hz'], r['over_pct']))
    print()
    print('impliedHz = 1/mean per-frame CPU cost.  A 30 Hz camera needs <= 0.0333 s')
    print('per frame; anything above that means frames arrive faster than they are')
    print('consumed and the queue grows (i.e. the estimator silently drops rate).')
    print()
    for r in rows:
        print('  %-30s frames=%d cpu_p50=%.4fs cpu_max=%.4fs over_budget=%d (%.1f%%)'
              % (r['label'], r['qgt_frames'], r['cpu_p50'], r['cpu_max'],
                 r['over_budget'], r['over_pct']))


if __name__ == '__main__':
    main()
