#!/usr/bin/env python3
"""验证VISION_POSITION_ESTIMATE消息编码并发送测试"""
from pymavlink import mavutil
import time

port = '/dev/ttyACM0'
master = mavutil.mavlink_connection(port, baud=921600)
master.wait_heartbeat(timeout=10)
print(f"连接成功, sysid={master.target_system}, compid={master.target_component}")

# 构造消息
msg = master.mav.vision_position_estimate_encode(
    int(time.time() * 1e6),
    1.0, 2.0, 3.0,
    0.1, 0.2, 0.3)

# 打印消息信息
print(f"\n=== 消息编码验证 ===")
print(f"消息名: {msg.get_type()}")
print(f"消息ID: {msg.get_msgId()}")
print(f"字段名: {msg.get_fieldnames()}")
print(f"字段值: x={msg.x}, y={msg.y}, z={msg.z}, roll={msg.roll}, pitch={msg.pitch}, yaw={msg.yaw}")
print(f"usec={msg.usec}, reset_counter={msg.reset_counter}")
print(f"covariance长度: {len(msg.covariance) if msg.covariance else 0}")

# 打包帧
buf = msg.pack(master.mav)
print(f"帧长度: {len(buf)} 字节")
print(f"帧hex前24字节: {buf[:24].hex()}")

# 发送并确认写入
written = master.port.write(buf)
print(f"串口写入: {written} 字节")

# 等1秒后读飞控响应（确认链路双向OK）
time.sleep(1)
resp = master.recv_match(type=['HEARTBEAT', 'SYS_STATUS'], blocking=True, timeout=3)
if resp:
    print(f"飞控响应正常: {resp.get_type()}")

print("\n=== 完成 ===")
