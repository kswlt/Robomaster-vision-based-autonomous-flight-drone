#!/usr/bin/env python3
"""读取PX4 IMU频率相关参数（只读）"""
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
m.wait_heartbeat(timeout=10)
print('连接成功, sys=%d comp=%d' % (m.target_system, m.target_component))

for pname in [b'SENS_IMU_MAV_RATE', b'SENS_IMU_RATE', b'IMU_INTEG_RATE', b'SENS_FLOW_MINHGT']:
    try:
        m.mav.param_request_read_send(m.target_system, m.target_component, pname, -1)
        msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
        if msg:
            print('%s = %s' % (msg.param_id, msg.param_value))
        else:
            print('%s = (无响应)' % pname)
    except Exception as e:
        print('%s 读取失败: %s' % (pname, e))
    time.sleep(0.2)
