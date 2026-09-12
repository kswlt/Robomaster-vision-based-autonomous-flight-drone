#!/usr/bin/env python3
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
m.wait_heartbeat(timeout=10)
print(f"连接成功")

for name in ['MAV_4_MODE', 'MAV_4_RATE', 'MAV_0_MODE', 'MAV_PROTO_VER', 'MAV_4_FWD']:
    m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
    msg = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if msg:
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode()
        pid = pid.strip('\x00').strip()
        if pid == name:
            print(f"{name} = {msg.param_value}")
        else:
            print(f"{name} = (读到其他: {pid})")
    else:
        print(f"{name} = (超时)")
    time.sleep(0.2)
