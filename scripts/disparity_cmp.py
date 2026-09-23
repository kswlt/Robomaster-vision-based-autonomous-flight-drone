#!/usr/bin/env python3
"""Compare discontinuity / disparity statistics between a live log and replay logs.

The ZUPT disparity gate is `disp_avg < zupt_max_disparity (0.5 px)`.  If the same
bag produces very different disparity distributions live vs offline, then the
in-camera feature-tracking state differs, which changes what ZUPT can even see.
"""
import re
import sys
import glob

ANSI = re.compile(r'\x1b\[[0-9;]*m')
ZP = re.compile(r'^\[ZUPT\]: passed disparity \(([\d.]+) < ([\d.]+), (\d+) features\)')
ZFA = re.compile(r'^\[ZUPT\]: failed disparity \(([\d.]+) > ([\d.]+), (\d+) features\)')
INIT = re.compile(r'^\[init\]: disparity is ([\d.]+),([\d.]+) \(([\d.]+) thresh\)')


def stats(v):
    if not v:
        return None
    v2 = sorted(v)
    n = len(v2)
    q = lambda t: v2[min(n - 1, max(0, int(t * (n - 1))))]
    return dict(n=n, mean=sum(v2) / n, min=v2[0], p50=q(.5), p95=q(.95),
                p99=q(.99), max=v2[-1])


def analyse(path, label):
    zpass, zfail, init_d, feats, frames = [], [], [], [], 0
    try:
        fh = open(path, 'r', encoding='utf-8', errors='replace')
    except Exception:
        return None
    for ln in fh:
        s = ANSI.sub('', ln).strip()
        if s.startswith('q_GtoI'):
            frames += 1
        m = ZP.match(s)
        if m:
            zpass.append(float(m.group(1))); feats.append(int(m.group(3))); continue
        m = ZFA.match(s)
        if m:
            zfail.append(float(m.group(1))); continue
        m = INIT.match(s)
        if m:
            init_d.append(float(m.group(1))); init_d.append(float(m.group(2)))
    return dict(label=label, frames=frames, zpass=zpass, zfail=zfail,
                init_d=init_d, feats=feats)


def show(r):
    print('--- %s ---' % r['label'])
    print('  q_GtoI frames = %d' % r['frames'])
    sp = stats(r['zpass'])
    if sp:
        print('  ZUPT passed disparity : n=%d mean=%.4f p50=%.4f p95=%.4f p99=%.4f max=%.4f'
              % (sp['n'], sp['mean'], sp['p50'], sp['p95'], sp['p99'], sp['max']))
        print('  pass coverage         : %d/%d = %.1f%% of frames'
              % (sp['n'], r['frames'], 100.0 * sp['n'] / max(1, r['frames'])))
    else:
        print('  ZUPT passed disparity : none')
    sf = stats(r['zfail'])
    if sf:
        print('  ZUPT FAILED disparity : n=%d mean=%.4f p50=%.4f max=%.4f'
              % (sf['n'], sf['mean'], sf['p50'], sf['max']))
    else:
        print('  ZUPT FAILED disparity : none logged (PRINT_DEBUG is invisible at INFO)')
    sd = stats(r['init_d'])
    if sd:
        print('  init-stage disparity  : n=%d mean=%.4f p50=%.4f max=%.4f'
              % (sd['n'], sd['mean'], sd['p50'], sd['max']))
    sf2 = stats(r['feats'])
    if sf2:
        print('  features at ZUPT      : mean=%.1f p50=%.0f min=%d max=%d'
              % (sf2['mean'], sf2['p50'], int(sf2['min']), int(sf2['max'])))
    print()


def main():
    for p in sys.argv[1:]:
        r = analyse(p, p.split('/')[-1])
        if r:
            show(r)
    print('NOTE: the ZUPT reject path is PRINT_DEBUG, so at verbosity INFO only the')
    print('"passed disparity" lines appear.  A low pass-coverage therefore means the')
    print('disparity gate itself rejected, or ZUPT was never reached, for the rest.')


if __name__ == '__main__':
    main()
