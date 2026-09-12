#!/usr/bin/env python3
from pymavlink import mavutil

m = mavutil.mavlink_connection('udpout:127.0.0.1:14551')

# 方案A：encode后手动填covariance
msg = m.mav.vision_position_estimate_encode(0, 1.0, 2.0, 3.0, 0, 0, 0)
print("=== 方案A: 7字段encode + 手动填covariance ===")
print("fieldnames:", msg.get_fieldnames())
print("lengths:", getattr(msg, 'lengths', None))
print("array_lengths:", getattr(msg, 'array_lengths', None))
print("orders:", getattr(msg, 'orders', None))
print("native_format:", getattr(msg, 'native_format', None))

buf_a = msg.pack(m.mav)
print(f"pack后帧长度: {len(buf_a)} (44=7字段, 更大=含covariance)")

# 尝试填covariance
try:
    msg.covariance = [0.1] * 21
    msg.reset_counter = 0
    buf_a2 = msg.pack(m.mav)
    print(f"填covariance后帧长度: {len(buf_a2)}")
    print(f"hex前30: {buf_a2[:30].hex()}")
except Exception as e:
    print(f"填covariance失败: {e}")

# 方案B：检查encode签名是否支持covariance参数
import inspect
try:
    sig = inspect.signature(m.mav.vision_position_estimate_encode)
    print(f"\nencode签名: {sig}")
except Exception as e:
    print(f"签名检查失败: {e}")

try:
    msg2 = m.mav.vision_position_estimate_encode(0, 1.0, 2.0, 3.0, 0, 0, 0, [0.1]*21, 0)
    buf_b = msg2.pack(m.mav)
    print(f"方案B(9参数)帧长度: {len(buf_b)}")
except Exception as e:
    print(f"方案B失败: {e}")
