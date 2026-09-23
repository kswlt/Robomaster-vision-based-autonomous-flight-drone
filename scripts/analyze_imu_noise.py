#!/usr/bin/env python3
"""Stationary IMU descriptive statistics; short runs do not establish noise densities."""
import argparse
import json
from pathlib import Path
import numpy as np
from analyze_sensor_timing import read_bag, distribution, stream_stats


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('bag')
    p.add_argument('--stationary-confirmed',action='store_true')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    if not a.stationary_confirmed:
        p.error('Operator stationary confirmation required')
    t,g,acc=[],[],[]
    for _,m,_ in read_bag(a.bag,['/imu']):
        t.append(m.header.stamp.sec*10**9+m.header.stamp.nanosec)
        g.append([m.angular_velocity.x,m.angular_velocity.y,m.angular_velocity.z])
        acc.append([m.linear_acceleration.x,m.linear_acceleration.y,m.linear_acceleration.z])
    if len(t)<2:
        raise SystemExit('Missing IMU')
    gyro=np.array(g)
    accel=np.array(acc)
    elapsed=(np.asarray(t,dtype=np.int64)-t[0])*1e-9
    windows=[]
    for start in range(0,int(elapsed[-1]),10):
        select=(elapsed>=start)&(elapsed<start+10)
        if select.sum():
            windows.append(dict(start_sec=start,count=int(select.sum()),gyro_mean=gyro[select].mean(axis=0).tolist(),accel_mean=accel[select].mean(axis=0).tolist()))
    report=dict(status='DESCRIPTIVE_STATISTICS_ONLY',duration_sec=float(elapsed[-1]),
                five_minute_requirement_met=bool(elapsed[-1]>=300),gyro_mean_radps=gyro.mean(axis=0).tolist(),
                gyro_std_radps=gyro.std(axis=0).tolist(),accel_mean_mps2=accel.mean(axis=0).tolist(),
                accel_std_mps2=accel.std(axis=0).tolist(),accel_norm_mps2=distribution(np.linalg.norm(accel,axis=1)),
                gyro_norm_radps=distribution(np.linalg.norm(gyro,axis=1)),timing=stream_stats(t),ten_second_bias_windows=windows,
                gyro_noise_density=None,accel_noise_density=None,bias_random_walk=None,
                limitation='No Allan variance fitted; sample std includes vibration, bias and filtering. Do not substitute it for continuous-time YAML noise density.')
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in report.items() if k!='ten_second_bias_windows'},indent=2))


if __name__=='__main__':
    main()
