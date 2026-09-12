#!/usr/bin/env python3
"""重启PX4飞控"""
from pymavlink import mavutil
import time

port = '/dev/ttyACM0'
master = mavutil.mavlink_connection(port, baud=921600)
master.wait_heartbeat(timeout=10)
print(f"连接成功, 发送重启命令...")

# MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, param1=1 表示重启
master.mav.command_long_send(
    master.target_system, master.target_component,
    mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
    0, 1, 0, 0, 0, 0, 0, 0)

print("重启命令已发送，飞控即将重启")
time.sleep(2)
