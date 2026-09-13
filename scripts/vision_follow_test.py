#!/usr/bin/env python3
"""决定性测试：发送已知VISION数据，看飞控EKF位置是否跟随"""
from pymavlink import mavutil
import time

port = '/dev/ttyACM0'
master = mavutil.mavlink_connection(port, baud=921600)
master.wait_heartbeat(timeout=10)
print(f"连接成功")
master.srcSystem = 42
master.srcComponent = 197  # MAV_COMP_ID_VISUAL_INERTIAL_ODOMETRY

# 请求LOCAL_POSITION_NED流 (10Hz)
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
    32, 100000, 0, 0, 0, 0, 0)  # LOCAL_POSITION_NED=32, 100ms

time.sleep(1)

def get_local_pos(timeout=3):
    """读一条LOCAL_POSITION_NED"""
    end = time.time() + timeout
    while time.time() < end:
        msg = master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=timeout)
        if msg:
            return msg
    return None

def send_vision(x, y, z, n=20, interval=0.5):
    """连续发送VISION_POSITION_ESTIMATE"""
    for i in range(n):
        msg = master.mav.vision_position_estimate_encode(
            int(time.time() * 1e6), x, y, z, 0.0, 0.0, 0.0)
        master.port.write(msg.pack(master.mav))
        time.sleep(interval)

print("\n=== 测试1: 发送VISION z=3.0 (x=1,y=2) 持续10秒 ===")
send_vision(1.0, 2.0, 3.0)
time.sleep(2)
pos = get_local_pos()
if pos:
    print(f"EKF位置: x={pos.x:.2f}, y={pos.y:.2f}, z={pos.z:.2f}")
    print(f"期望跟随: x≈1, y≈2, z≈3 (如果视觉被融合)")
else:
    print("没收到LOCAL_POSITION_NED!")

print("\n=== 测试2: 发送VISION z=5.0 (x=4,y=6) 持续10秒 ===")
send_vision(4.0, 6.0, 5.0)
time.sleep(2)
pos = get_local_pos()
if pos:
    print(f"EKF位置: x={pos.x:.2f}, y={pos.y:.2f}, z={pos.z:.2f}")
    print(f"期望跟随: x≈4, y≈6, z≈5 (如果视觉被融合)")
else:
    print("没收到LOCAL_POSITION_NED!")

print("\n=== 测试3: 读ESTIMATOR_STATUS确认视觉融合位 ===")
msg = master.recv_match(type='ESTIMATOR_STATUS', blocking=True, timeout=3)
if msg:
    print(f"flags={msg.flags} posH={msg.pos_horiz_ratio} posV={msg.pos_vert_ratio}")
    print(f"  bit3(8)=POS_HORIZ_REL(水平相对位置有效): {'YES' if msg.flags & 8 else 'NO'}")
    print(f"  bit1(2)=VELOCITY_HORIZ(水平速度有效): {'YES' if msg.flags & 2 else 'NO'}")
    print("  注意：这些是解状态有效位，不代表特定的视觉/光流融合源。")

print("\n=== 完成 ===")
