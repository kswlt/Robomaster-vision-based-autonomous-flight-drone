#!/usr/bin/env python3
"""测试pymavlink 2.4.49连接和covariance发送"""
import sys

# 先检查当前版本
try:
    import pymavlink
    import pymavlink.mavutil as mavutil
    print(f"当前pymavlink版本: {getattr(pymavlink, '__version__', 'unknown')}")
except ImportError as e:
    print(f"导入失败: {e}")
    sys.exit(1)

from pymavlink import mavutil

# 测试encode签名
m = mavutil.mavlink_connection('udpout:127.0.0.1:14551')
import inspect
try:
    sig = inspect.signature(m.mav.vision_position_estimate_encode)
    print(f"VISION_POSITION_ESTIMATE.encode签名: {sig}")
except Exception as e:
    print(f"签名检查: {e}")

# 测试9参数encode
try:
    msg = m.mav.vision_position_estimate_encode(0, 1.0, 2.0, 3.0, 0, 0, 0, [0.1]*21, 0)
    buf = msg.pack(m.mav)
    print(f"9参数encode帧长度: {len(buf)} (期望>100=含covariance)")
    print(f"hex前20: {buf[:20].hex()}")
except Exception as e:
    print(f"9参数encode失败: {e}")
