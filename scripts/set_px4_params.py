#!/usr/bin/env python3
"""设置PX4 VIO关键参数并验证"""
from pymavlink import mavutil
import time

port = '/dev/ttyACM0'
master = mavutil.mavlink_connection(port, baud=921600)
master.wait_heartbeat(timeout=10)
print(f"连接成功, 系统ID: {master.target_system}")

INT32 = mavutil.mavlink.MAV_PARAM_TYPE_INT32
REAL32 = mavutil.mavlink.MAV_PARAM_TYPE_REAL32

def set_and_verify(name, value, ptype):
    """设置参数并读回验证"""
    master.mav.param_set_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), value, ptype)
    # 等待飞控确认（可能返回设置后的PARAM_VALUE）
    time.sleep(0.5)
    # 读回验证
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=3)
    if msg:
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode('utf-8')
        pid = pid.strip('\x00').strip()
        if pid == name:
            print(f"✓ {name} = {msg.param_value} (目标: {value})")
            return msg.param_value
    print(f"✗ {name} 验证失败")
    return None

# 设置参数
print("=== 设置VIO参数 ===")
set_and_verify('EKF2_EV_CTRL', 11, INT32)     # 水平位置+垂直位置+偏航
set_and_verify('EKF2_HGT_REF', 3, INT32)      # 视觉高度
set_and_verify('EKF2_EV_DELAY', 50, REAL32)   # 视觉延迟50ms

# 额外确认MAVLink实例配置
print("\n=== 检查MAVLink实例 ===")
for name in ['MAV_4_MODE', 'MAV_4_RATE']:
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    if msg:
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode('utf-8')
        pid = pid.strip('\x00').strip()
        print(f"{pid} = {msg.param_value}")
    else:
        print(f"{name} = (不存在)")

print("\n完成，请重启飞控使参数完全生效")
