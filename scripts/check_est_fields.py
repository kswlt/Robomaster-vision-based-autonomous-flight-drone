#!/usr/bin/env python3
"""查ESTIMATOR_STATUS消息的字段"""
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
m.wait_heartbeat(timeout=10)
print("连接成功")

# 请求ESTIMATOR_STATUS流
m.mav.request_data_stream_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 10, 1)

time.sleep(1)
msg = m.recv_match(type='ESTIMATOR_STATUS', blocking=True, timeout=5)
if msg:
    print("ESTIMATOR_STATUS字段:")
    for attr in dir(msg):
        if not attr.startswith('_'):
            print(f"  {attr}")
    print("\n关键值:")
    print(f"  flags={msg.flags}")
    print(f"  innovation_ratios={getattr(msg, 'innovation_ratios', 'N/A')}")
    for a in ['pos_horiz_ratio', 'pos_vert_ratio', 'vel_horiz_ratio', 'vel_vert_ratio',
              'pos_horiz_accuracy', 'pos_vert_accuracy', 'vel_horiz_accuracy']:
        if hasattr(msg, a):
            print(f"  {a}={getattr(msg, a)}")
else:
    print("没收到ESTIMATOR_STATUS")
