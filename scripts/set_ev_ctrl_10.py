#!/usr/bin/env python3
"""设置EKF2_EV_CTRL=10（水平+垂直位置，不融合偏航）"""
from pymavlink import mavutil
import time

master = mavutil.mavlink_connection('/dev/ttyACM0', baud=921600)
master.wait_heartbeat(timeout=10)
print("连接成功")

INT32 = mavutil.mavlink.MAV_PARAM_TYPE_INT32

# 设置EKF2_EV_CTRL=10 (bit0水平位置 + bit1垂直位置, 不融合偏航)
master.mav.param_set_send(
    master.target_system, master.target_component,
    b'EKF2_EV_CTRL', 10, INT32)
time.sleep(1)

# 读回验证
master.mav.param_request_read_send(
    master.target_system, master.target_component,
    b'EKF2_EV_CTRL', -1)
msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
if msg:
    pid = msg.param_id
    if isinstance(pid, bytes):
        pid = pid.decode()
    pid = pid.strip('\x00').strip()
    if pid == 'EKF2_EV_CTRL':
        print(f"EKF2_EV_CTRL = {msg.param_value} (目标10)")
    else:
        print(f"读到其他: {pid}")
else:
    print("读取超时")
