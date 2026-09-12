#!/usr/bin/env python3
"""检查GPS状态和EKF2参数"""
from pymavlink import mavutil
import time

port = '/dev/ttyACM0'
master = mavutil.mavlink_connection(port, baud=921600)
master.wait_heartbeat(timeout=10)
print(f"连接成功")
master.srcSystem = 42
master.srcComponent = 191

# 请求GPS_RAW_INT (24) 和 SYS_STATUS (1) 流
for msg_id, interval_us in [(24, 500000), (1, 500000)]:
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
        msg_id, interval_us, 0, 0, 0, 0, 0)

time.sleep(1)

# 读GPS
gps = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=3)
if gps:
    print(f"GPS: fix_type={gps.fix_type}, satellites={gps.satellites_visible}, "
          f"eph={gps.eph}, lat={gps.lat}, lon={gps.lon}, alt={gps.alt}")
else:
    print("GPS: 无GPS_RAW_INT消息（可能没有GPS模块）")

# 读参数
print("\n=== EKF2参数 ===")
for name in ['EKF2_EV_CTRL', 'EKF2_GPS_CTRL', 'EKF2_HGT_REF', 'SYS_HAS_GPS', 'SYS_HAS_MAG']:
    master.mav.param_request_read_send(
        master.target_system, master.target_component,
        name.encode('utf-8'), -1)
    msg = master.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    if msg:
        pid = msg.param_id
        if isinstance(pid, bytes):
            pid = pid.decode('utf-8')
        pid = pid.strip('\x00').strip()
        if pid == name:
            print(f"{name} = {msg.param_value}")
        else:
            print(f"{name} = (读到别的: {pid})")
    else:
        print(f"{name} = (超时/不存在)")

print("\n完成")
