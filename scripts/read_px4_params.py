#!/usr/bin/env python3
"""读取PX4关键参数，确认VIO相关配置"""
from pymavlink import mavutil
import time

port = '/dev/ttyACM0'
try:
    master = mavutil.mavlink_connection(port, baud=921600)
    master.wait_heartbeat(timeout=10)
    print(f"连接成功, 系统ID: {master.target_system}")

    params = ['EKF2_EV_CTRL', 'EKF2_HGT_REF', 'EKF2_EV_DELAY',
              'MAV_4_MODE', 'MAV_4_RATE', 'EKF2_AID_MASK', 'EKF2_EV_NOISE']

    for name in params:
        master.mav.param_request_read_send(
            master.target_system, master.target_component,
            name.encode('utf-8'), -1)
        msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode('utf-8')
        pid = pid.strip('\x00').strip()
        if msg and pid == name:
            print(f"{name} = {msg.param_value}")
        else:
            print(f"{name} = (读取超时/不存在, 实际={pid})")
        time.sleep(0.2)

except Exception as e:
    print(f"错误: {e}")

print("完成")
