#!/usr/bin/env python3
"""Score a labeled stationary bag; never treat an unlabeled bag as ground truth."""
import argparse
import json
from pathlib import Path
import numpy as np
from analyze_sensor_timing import read_bag, distribution


def score(stamps_ns, positions, velocities, variances, seconds=120):
    t=np.asarray(stamps_ns,dtype=np.int64)
    p=np.asarray(positions,dtype=float)
    v=np.asarray(velocities,dtype=float)
    c=np.asarray(variances,dtype=float)
    if len(t)<2:
        return dict(status='INVALID_NO_ODOMETRY', count=len(t))
    elapsed=(t-t[0])*1e-9
    finite=bool(np.isfinite(p).all() and np.isfinite(v).all() and np.isfinite(c).all())
    monotonic=bool((np.diff(t)>0).all())
    if not finite or not monotonic:
        return dict(status='FAIL_NONFINITE_OR_NONMONOTONIC',finite=finite,monotonic=monotonic,count=len(t))
    end=min(float(elapsed[-1]),seconds)
    idx=elapsed<end
    tt=np.r_[elapsed[idx],end]
    pp=np.vstack([p[idx], [np.interp(end,elapsed,p[:,k]) for k in range(3)]])
    vv=np.vstack([v[idx], [np.interp(end,elapsed,v[:,k]) for k in range(3)]])
    speed=np.linalg.norm(vv,axis=1)
    drift=np.linalg.norm(pp-pp[0],axis=1)
    rms=float(np.sqrt(np.trapz(speed**2,tt)/end)) if end>0 else None
    full=end>=seconds
    max_cov=float(np.max(c[elapsed<=end]))
    passed=full and float(drift.max())<.05 and rms<.03 and max_cov<=4
    return dict(status='PASS_STATIC_ENGINEERING_GATE' if passed else 'FAIL_OR_INCOMPLETE_STATIC_GATE',
                count=len(t),full_odometry_span_sec=float(elapsed[-1]),scored_seconds=end,
                required_seconds=seconds,complete_window=full,position_endpoint_drift_m=float(drift[-1]),
                position_peak_drift_m=float(drift.max()),velocity_rms_mps=rms,velocity_max_mps=float(speed.max()),
                position_variance_max_m2=max_cov,finite=finite,monotonic=monotonic,
                ground_truth='OPERATOR DECLARED STATIONARY; NO EXTERNAL GROUND TRUTH',
                limitation='STATIC pass does not establish dynamic performance; current ZUPT can mask estimator drift')


def main():
    a=argparse.ArgumentParser(__doc__)
    a.add_argument('bag')
    a.add_argument('--stationary-confirmed',action='store_true')
    a.add_argument('--output',required=True)
    args=a.parse_args()
    if not args.stationary_confirmed:
        a.error('Requires explicit operator stationary confirmation')
    t,p,v,c=[],[],[],[]
    for topic,m,_ in read_bag(args.bag,['/odomimu']):
        t.append(m.header.stamp.sec*10**9+m.header.stamp.nanosec)
        p.append([m.pose.pose.position.x,m.pose.pose.position.y,m.pose.pose.position.z])
        v.append([m.twist.twist.linear.x,m.twist.twist.linear.y,m.twist.twist.linear.z])
        c.append([m.pose.covariance[k] for k in (0,7,14)])
    result=score(t,p,v,c)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
