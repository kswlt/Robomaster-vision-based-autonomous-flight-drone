#!/usr/bin/env python3
import rosbag2_py, numpy as np
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
import sys
path=sys.argv[1]
r=rosbag2_py.SequentialReader(); r.open(rosbag2_py.StorageOptions(uri=path, storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
types={t.name:get_message(t.type) for t in r.get_all_topics_and_types()}
r.set_filter(rosbag2_py.StorageFilter(topics=['/imu']))
ts=[]; gz=[]; ax=[]; ay=[]; az=[]; gx=[]; gy=[]
while r.has_next():
    top,data,_=r.read_next(); m=deserialize_message(data,types[top])
    t=m.header.stamp.sec+m.header.stamp.nanosec*1e-9
    ts.append(t); gz.append(m.angular_velocity.z); gx.append(m.angular_velocity.x); gy.append(m.angular_velocity.y)
    ax.append(m.linear_acceleration.x); ay.append(m.linear_acceleration.y); az.append(m.linear_acceleration.z)
ts=np.array(ts); trel=ts-ts[0]
gz=np.array(gz); gx=np.array(gx); gy=np.array(gy)
ax=np.array(ax); ay=np.array(ay); az=np.array(az)
print('IMU n=%d last=%.1f' % (len(ts), trel[-1]))
act = np.abs(gx)+np.abs(gy)+np.abs(gz)
for a in range(0, int(trel[-1])+1, 5):
    m=(trel>=a)&(trel<a+5)
    if m.sum():
        print(' t=%3d-%3d |w|max=%.3f |a|max=%.2f' % (a, a+5, act[m].max(), np.linalg.norm(np.stack([ax[m],ay[m],az[m]]),axis=0).max()))
