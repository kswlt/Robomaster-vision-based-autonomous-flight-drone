#!/usr/bin/env python3
"""检查光流相关配置：TELEM2/MAV_1 + SENS_FLOW"""
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

names = ['MAV_1_CONFIG', 'MAV_1_MODE', 'SER_TEL2_BAUD', 'MAV_1_RATE',
         'SENS_FLOW_ROT', 'SENS_FLOW_ADDR', 'SENS_FLOW_MINHGT', 'SENS_FLOW_MAXHGT',
         'EKF2_RNG_CTRL', 'EKF2_RNG_DELAY', 'EKF2_RNG_PITCH',
         'EKF2_EV_CTRL', 'SYS_HAS_GPS', 'SYS_HAS_MAG']
for n in names:
    v = read_param(n)
    print(f"{n} = {v}")
