#!/usr/bin/env python3
"""Inspect PX4 MAVLink clock relationships without sending vision data."""

import argparse
import statistics
import time
import json
from pathlib import Path
import numpy as np
from analyze_sensor_timing import distribution

from pymavlink import mavutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--output", default="results/vio_validation/px4_timebase.json")
    parser.add_argument("--exclusive-serial", action="store_true", help="Required: stop the bridge before opening its serial port")
    args = parser.parse_args()
    if not args.exclusive_serial or args.seconds < 60:
        parser.error('Stop the bridge, use --exclusive-serial, and record >=60 seconds')

    master = mavutil.mavlink_connection(args.port, baud=args.baud)
    heartbeat = master.wait_heartbeat(timeout=10)
    if heartbeat is None:
        raise SystemExit("PX4 heartbeat timeout")

    # Request only the two diagnostic streams used below.
    for message_id, interval_us in ((234, 10_000), (2, 200_000)):
        master.mav.command_long_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
            0,
            message_id,
            interval_us,
            0,
            0,
            0,
            0,
            0,
        )

    boot_epoch = None
    arrival_lag = []
    raw_offsets = []
    offset_times = []
    imu_intervals = []
    accel_norms = []
    gyro_norms = []
    last_imu_us = None
    imu_count = 0
    system_count = 0
    deadline = time.monotonic() + args.seconds

    while time.monotonic() < deadline:
        msg = master.recv_match(
            type=["HIGHRES_IMU", "SYSTEM_TIME"], blocking=True, timeout=1.0
        )
        if msg is None:
            continue
        arrival = time.time()
        if msg.get_type() == "SYSTEM_TIME":
            unix_us = int(msg.time_unix_usec)
            boot_ms = int(msg.time_boot_ms)
            system_count += 1
            if unix_us > 1_000_000_000_000:
                boot_epoch = unix_us * 1e-6 - boot_ms * 1e-3
                print(
                    f"SYSTEM_TIME unix={unix_us} boot_ms={boot_ms} "
                    f"arrival_minus_px4={arrival - unix_us * 1e-6:+.6f}s"
                )
            else:
                print(f"SYSTEM_TIME invalid unix={unix_us} boot_ms={boot_ms}")
            continue

        imu_us = int(msg.time_usec)
        imu_count += 1
        accel_norms.append(
            (float(msg.xacc) ** 2 + float(msg.yacc) ** 2 + float(msg.zacc) ** 2)
            ** 0.5
        )
        gyro_norms.append(
            (float(msg.xgyro) ** 2 + float(msg.ygyro) ** 2 + float(msg.zgyro) ** 2)
            ** 0.5
        )
        if 0 < imu_us < 1_000_000_000_000:
            raw_offsets.append(arrival - imu_us * 1e-6)
            offset_times.append(time.monotonic())
        if last_imu_us is not None:
            imu_dt = (imu_us - last_imu_us) * 1e-6
            imu_intervals.append(imu_dt)
            if imu_dt < 0.0 or imu_dt > 0.020:
                print(
                    f"IMU_TIME_JUMP sample={imu_count} dt={imu_dt:+.6f}s "
                    f"previous={last_imu_us} current={imu_us}"
                )
        last_imu_us = imu_us
        if boot_epoch is not None and imu_us < 1_000_000_000_000:
            arrival_lag.append(arrival - (boot_epoch + imu_us * 1e-6))

    print(f"HIGHRES_IMU count={imu_count} SYSTEM_TIME count={system_count}")
    if imu_intervals:
        print(
            "IMU dt: "
            f"mean={statistics.mean(imu_intervals):.6f}s "
            f"stdev={statistics.pstdev(imu_intervals):.6f}s "
            f"min={min(imu_intervals):.6f}s max={max(imu_intervals):.6f}s"
        )
    if accel_norms:
        print(
            "Accel norm: "
            f"mean={statistics.mean(accel_norms):.6f}m/s^2 "
            f"stdev={statistics.pstdev(accel_norms):.6f}m/s^2 "
            f"min={min(accel_norms):.6f}m/s^2 max={max(accel_norms):.6f}m/s^2"
        )
    if gyro_norms:
        print(
            "Gyro norm: "
            f"mean={statistics.mean(gyro_norms):.6f}rad/s "
            f"stdev={statistics.pstdev(gyro_norms):.6f}rad/s "
            f"min={min(gyro_norms):.6f}rad/s max={max(gyro_norms):.6f}rad/s"
        )
    if arrival_lag:
        print(
            "Serial arrival lag versus PX4 SYSTEM_TIME mapping: "
            f"median={statistics.median(arrival_lag):+.6f}s "
            f"mean={statistics.mean(arrival_lag):+.6f}s "
            f"stdev={statistics.pstdev(arrival_lag):.6f}s "
            f"min={min(arrival_lag):+.6f}s max={max(arrival_lag):+.6f}s"
        )
    else:
        print("No valid PX4 boot-to-Unix mapping was available")
    if raw_offsets:
        first = raw_offsets[0]
        minimum = min(raw_offsets)
        print(
            "Arrival-minus-boot offset variation: "
            f"first_minus_min={first - minimum:+.6f}s "
            f"median_minus_min={statistics.median(raw_offsets) - minimum:+.6f}s "
            f"max_minus_min={max(raw_offsets) - minimum:+.6f}s"
        )

    master.close()
    elapsed = np.asarray(offset_times) - offset_times[0] if offset_times else np.array([])
    slope = float(np.polyfit(elapsed, np.asarray(raw_offsets)-raw_offsets[0], 1)[0]) if len(elapsed)>1 else None
    out = dict(duration_requested_sec=args.seconds, imu_count=imu_count, system_time_count=system_count,
               requested_imu_interval_us=10000, stream_request_ack_verified=False,
               sample_dt_sec=distribution(imu_intervals),
               negative_timestamp_count=sum(x<0 for x in imu_intervals),
               duplicate_timestamp_count=sum(x==0 for x in imu_intervals),
               arrival_lag_vs_system_time_sec=distribution(arrival_lag),
               arrival_offset_minus_min_sec=distribution(np.asarray(raw_offsets)-min(raw_offsets) if raw_offsets else []),
               arrival_offset_linear_slope_sec_per_sec=slope,
               caveat='Arrival-offset slope includes transport/scheduler delay; it is not independently established oscillator drift. SYSTEM_TIME mapping includes sender clock synchronization uncertainty.',
               offset_trend=[dict(elapsed_sec=float(t), arrival_minus_sensor_sec=o) for t,o in zip(elapsed,raw_offsets)])
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(out,indent=2,allow_nan=False))


if __name__ == "__main__":
    main()
