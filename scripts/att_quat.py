#!/usr/bin/env python3
import re, sys, numpy as np
logf = sys.argv[1]
lines = open(logf, errors='replace').read().splitlines()
pat = re.compile(r'q_GtoI = ([\-0-9., ]+?) \| p_IinG')
qs = []
for ln in lines:
    m = pat.search(ln)
    if m:
        try:
            q = [float(x) for x in m.group(1).split(',')]
            if len(q) == 4: qs.append(q)
        except ValueError: pass
q = np.array(qs)
print('n=%d' % len(q))
# incremental rotation angle per consecutive samples, then per-segment total
t = np.linspace(0, 79.6, len(q)) if len(q) > 1 else np.array([0])
def qmul(a, b):  # a * b (Hamilton)
    w1,x1,y1,z1 = a; w2,x2,y2,z2 = b
    return np.array([w1*w2-x1*x2-y1*y2-z1*z2, w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2])
def qang(qq):
    w = np.clip(qq[0], -1, 1)
    return 2*np.arccos(abs(w))
angs = np.zeros(len(q))
for i in range(1, len(q)):
    dq = qmul(q[i], q[i-1].conj() if hasattr(q[i-1], 'conj') else np.array([q[i-1][0], -q[i-1][1], -q[i-1][2], -q[i-1][3]]))
    angs[i] = qang(dq)
cum = np.cumsum(angs)
for name, a, b in [('static_0_20',0,20),('static_20_40',20,40),('static_40_60',40,60),('static_60_79',60,79.6),('total',0,79.6)]:
    m = (t>=a)&(t<b)
    if m.sum() >= 2:
        print(' %s: att change %.2f deg (%.4f deg/s)' % (name, np.degrees(cum[m][-1]-cum[m][0]), np.degrees((cum[m][-1]-cum[m][0])/(t[m][-1]-t[m][0]))))
print(' first q:', q[0].tolist(), ' last q:', q[-1].tolist())
