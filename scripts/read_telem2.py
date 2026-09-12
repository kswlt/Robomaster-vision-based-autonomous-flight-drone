#!/usr/bin/env python3
"""重读TELEM2相关参数（多轮排除干扰）"""
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
m.wait_heartbeat(timeout=10)
print(f"PX4连接成功 sys={m.target_system}")

def read_param(name, retries=5):
    for i in range(retries):
        m.mav.param_request_read_send(m.target_system, m.target_component,
                                      name.encode(), -1)
        for _ in range(50):
            msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
            if msg and msg.param_id.strip('\x00') == name:
                v = msg.param_value
                if 1e-30 < abs(v) < 1e30:  # 排除垃圾值
                    return v
                print(f"  {name} 第{i+1}轮读到异常值 {v}")
                break
    return None

for n in ['SER_TEL2_BAUD', 'MAV_1_MODE', 'MAV_1_RATE', 'MAV_1_FORWARD',
          'SER_TEL1_BAUD', 'MAV_0_MODE',
          'EKF2_RNG_CTRL', 'EKF2_RNG_AID', 'EKF2_RNG_USE_SPO']:
    v = read_param(n)
    print(f"{n} = {v}")
