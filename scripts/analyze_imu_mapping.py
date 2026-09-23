#!/usr/bin/env python3
"""Analyze sample/host/mapped clocks recorded inside the actual bridge path."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from analyze_sensor_timing import distribution


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('trace')
    p.add_argument('--output',required=True)
    a=p.parse_args()
    with open(a.trace) as f:
        rows=list(csv.DictReader(f))
    host=np.array([int(r['host_before_ns']) for r in rows],dtype=np.int64)
    mono=np.array([int(r['monotonic_ns']) for r in rows],dtype=np.int64)
    sensor=np.array([int(r['sensor_usec'])*1000 for r in rows],dtype=np.int64)
    mapped=np.array([int(r['mapped_sec'])*10**9+int(r['mapped_nanosec']) for r in rows],dtype=np.int64)
    if len(host)<2:
        raise SystemExit('Insufficient trace')
    elapsed=(mono-mono[0])*1e-9
    # Subtract integer epochs first to preserve submicrosecond precision.
    sensor_elapsed=(sensor-sensor[0])*1e-9
    residual=(host-host[0]-(sensor-sensor[0]))*1e-9
    windows=[]
    for start in range(int(elapsed[-1])):
        m=(elapsed>=start)&(elapsed<start+1)
        if m.sum()>=10:
            windows.append([float(elapsed[m].mean()),float(np.percentile(residual[m],5))])
    w=np.array(windows)
    slope=float(np.polyfit(w[:,0],w[:,1],1)[0]) if len(w)>2 else None
    corrected=residual-slope*elapsed if slope is not None else residual
    report=dict(count=len(host),elapsed_monotonic_sec=float(elapsed[-1]),
                px4_sample_span_sec=float(sensor_elapsed[-1]),sensor_dt_sec=distribution(np.diff(sensor)*1e-9),
                mapped_dt_sec=distribution(np.diff(mapped)*1e-9),host_dt_sec=distribution(np.diff(host)*1e-9),
                host_clock_minus_monotonic_change_sec=distribution((host-host[0]-(mono-mono[0]))*1e-9),
                host_minus_mapped_sec=distribution((host-mapped)*1e-9),
                host_minus_sensor_offset_change_sec=float(residual[-1]),
                lower_quantile_clock_slope_sec_per_sec=slope,
                detrended_arrival_residual_above_min_sec=distribution(corrected-corrected.min()),
                mapping_offset_net_change_sec=float((mapped[-1]-mapped[0]-(sensor[-1]-sensor[0]))*1e-9),
                mapping_adjustment_per_sample_sec=distribution((np.diff(mapped)-np.diff(sensor))*1e-9),
                one_second_lower_quantile_trend=windows,
                interpretation='Host timestamp sampled just before existing imu_timestamp; arrival residual includes driver/serial scheduling. Lower-quantile slope is an observed sensor-host trend, not independently proven crystal drift. No absolute latency reference.')
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in report.items() if k!='one_second_lower_quantile_trend'},indent=2))


if __name__=='__main__':
    main()
