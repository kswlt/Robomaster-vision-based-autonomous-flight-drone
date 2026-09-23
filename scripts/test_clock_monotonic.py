#!/usr/bin/env python3
"""Regression test: the mapper must never emit a non-monotonic stamp.

The first version of the re-anchoring path cleared `last_stamp` and then took an
arrival-derived value, which produced a -0.49 s backwards step on a real PX4
trace.  This drives a synthetic PX4 clock step through every strategy and asserts
monotonicity, so the bug cannot come back.
"""
import os
import sys

# imu_clock_mapper.py lives next to the bridge (repo root), while this test lives
# in scripts/, so search both.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (_HERE, os.path.dirname(_HERE)):
    if os.path.isfile(os.path.join(_cand, 'imu_clock_mapper.py')):
        sys.path.insert(0, _cand)
        break
from imu_clock_mapper import ImuClockMapper  # noqa: E402

RATE = 200.0
DT = 1.0 / RATE


def gen(n_steps=8000, step_at=4000, step_back=0.5, latency=0.003,
        jitter=0.0, seed=1):
    import random
    random.seed(seed)
    out = []
    t_px4 = 100000.0
    t_host = 1790000000.0
    for i in range(n_steps):
        if i == step_at:
            t_px4 -= step_back
        lat = latency + (abs(random.gauss(0, jitter)) if jitter else 0.0)
        out.append((t_px4, t_host + lat))
        t_px4 += DT
        t_host += DT
    return out


def run(mode, samples):
    m = ImuClockMapper(mode=mode, nominal_rate=RATE)
    prev = None
    viol = []
    for idx, (st, at) in enumerate(samples):
        s, d = m.update(st, at)
        if prev is not None and s <= prev:
            viol.append((idx, prev, s, s - prev))
        prev = s
    return viol, m.summary()


def main():
    ok = True
    cases = [
        ('clean stream', gen()),
        ('PX4 rewinds 0.5 s', gen()),
        ('PX4 jumps forward 0.5 s', gen(step_back=-0.5)),
        ('two steps', gen(n_steps=12000, step_at=3000)),
        ('with jitter', gen(jitter=0.002, seed=3)),
    ]
    for mode in ImuClockMapper.MODES:
        for name, samples in cases:
            viol, sm = run(mode, samples)
            status = 'OK' if not viol else 'VIOLATION'
            if viol:
                ok = False
            print('  %-8s %-26s %-10s violations=%-3d reanchor_backwards=%d '
                  'clock_resets=%d repairs=%d dt<100us=%d'
                  % (mode, name, status, len(viol), sm['n_reanchor_backwards'],
                     sm['n_clock_reset'], sm['n_repairs'], sm['n_repairs_bad_dt']))
            for idx, p, s, dd in viol[:3]:
                print('        at %d: %.6f -> %.6f (%+.6f)' % (idx, p, s, dd))
    print()
    print('RESULT: %s' % ('PASS - all strategies monotonic' if ok else 'FAIL'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
