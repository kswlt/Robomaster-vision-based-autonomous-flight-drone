#!/usr/bin/env python3
import rosbag2_py, numpy as np, sys
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
path = sys.argv[1]
r = rosbag2_py.SequentialReader()
r.open(rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
types = {t.name: get_message(t.type) for t in r.get_all_topics_and_types()}
r.set_filter(rosbag2_py.StorageFilter(topics=['/imu']))
ts=[]; ax=[]; ay=[]; az=[]; gx=[]; gy=[]; gz=[]
while r.has_next():
    top, data, _ = r.read_next()
    m = deserialize_message(data, types[top])
    t = m.header.stamp.sec + m.header.stamp.nanosec*1e-9
    ts.append(t); ax.append(m.linear_acceleration.x); ay.append(m.linear_acceleration.y); az.append(m.linear_acceleration.z)
    gx.append(m.angular_velocity.x); gy.append(m.angular_velocity.y); gz.append(m.angular_velocity.z)
ts = np.array(ts); trel = ts - ts[0]
dt = np.diff(trel)
ax = np.array(ax); ay = np.array(ay); az = np.array(az)
gx = np.array(gx); gy = np.array(gy); gz = np.array(gz)
print('== IMU AUDIT ==')
print('n=%d dur=%.2fs rate=%.1f Hz' % (len(ts), trel[-1], len(ts)/trel[-1]))
print('dt: mean=%.6f std=%.6f min=%.6f max=%.6f P95=%.6f P99=%.6f' % (dt.mean(), dt.std(), dt.min(), dt.max(), np.percentile(dt,95), np.percentile(dt,99)))
print('dt > 2x mean: %d samples' % ((dt > 2*dt.mean()).sum()))
print('gaps > 0.1s:', [(float(trel[i]), float(dt[i])) for i in np.where(dt > 0.1)[0]][:5])
print('duplicate stamps: %d' % ((dt <= 0).sum()))
print('backward stamps: %d' % ((dt < 0).sum()))
# static noise (first 20s, assume static)
m0 = trel < 20
if m0.sum() > 10:
    print('static 0-20s acc mean: x=%.6f y=%.6f z=%.6f  std: x=%.6f y=%.6f z=%.6f' % (ax[m0].mean(), ay[m0].mean(), az[m0].mean(), ax[m0].std(), ay[m0].std(), az[m0].std()))
    print('static 0-20s gyro std: x=%.6f y=%.6f z=%.6f rad/s  (noise density @195Hz = std*sqrt(dt))' % (gx[m0].std(), gy[m0].std(), gz[m0].std()))
    print('  gyro noise density: x=%.2e y=%.2e z=%.2e rad/s/rtHz' % (gx[m0].std()*np.sqrt(dt[m0].mean()), gy[m0].std()*np.sqrt(dt[m0].mean()), gz[m0].std()*np.sqrt(dt[m0].mean())))
    print('  acc noise density: x=%.2e y=%.2e z=%.2e m/s2/rtHz' % (ax[m0].std()*np.sqrt(dt[m0].mean()), ay[m0].std()*np.sqrt(dt[m0].mean()), az[m0].std()*np.sqrt(dt[m0].mean())))
# acc drift trend (last static block)
m1 = trel > trel[-1]-20
if m1.sum() > 10:
    print('static last20s acc mean: x=%.6f y=%.6f z=%.6f  (drift vs first: %+.6f %+.6f %+.6f)' % (ax[m1].mean(), ay[m1].mean(), az[m1].mean(), ax[m1].mean()-ax[m0].mean(), ay[m1].mean()-ay[m0].mean(), az[m1].mean()-az[m0].mean()))
