#!/usr/bin/env python3
"""设置EKF2_EV_CTRL=3（水平位置+垂直位置，不融合视觉速度/偏航），并读回验证"""
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
m.wait_heartbeat(timeout=10)
print(f"PX4连接成功 sys={m.target_system} comp={m.target_component}")

def set_param(name, value):
    m.mav.param_set_send(m.target_system, m.target_component,
                         name.encode(), value, mavutil.mavlink.MAV_PARAM_TYPE_INT32)
    time.sleep(1.0)

def read_param(name):
    m.mav.param_request_read_send(m.target_system, m.target_component,
                                  name.encode(), -1)
    msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=5)
    if msg:
        return msg.param_value
    return None

set_param('EKF2_EV_CTRL', 3)
time.sleep(0.5)

for name in ['EKF2_EV_CTRL', 'EKF2_HGT_REF', 'EKF2_EV_DELAY']:
    v = read_param(name)
    print(f"{name} = {v}")

# 光流相关参数检查（只读）
print("\n--- 光流参数 ---")
for name in ['SENS_FLOW_MINHGT', 'EKF2_FLOW_DELAY', 'EKF2_RNG_AID', 'EKF2_RNG_CTRL']:
    v = read_param(name)
    print(f"{name} = {v}")
