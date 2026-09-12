#!/usr/bin/env python3
"""干净读取参数（校验param_id匹配）"""
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
m.wait_heartbeat(timeout=10)
print(f"PX4连接成功 sys={m.target_system}")

def read_param(name):
    m.mav.param_request_read_send(m.target_system, m.target_component,
                                  name.encode(), -1)
    for _ in range(50):
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
        if msg and msg.param_id.strip('\x00') == name:
            return msg.param_value
    return None

names = ['EKF2_EV_CTRL', 'EKF2_HGT_REF', 'EKF2_EV_DELAY',
         'SENS_FLOW_MINHGT', 'SENS_FLOW_MAXHGT', 'EKF2_FLOW_DELAY',
         'EKF2_RNG_AID', 'EKF2_RNG_CTRL', 'EKF2_GPS_CTRL']
for n in names:
    v = read_param(n)
    print(f"{n} = {v}")
