#!/usr/bin/env python3
"""测试v20.common方言的VISION_POSITION_ESTIMATE"""
import inspect

# 方案1: 用v20.common方言
try:
    from pymavlink.dialects.v20 import common as mavlink20
    m = mavlink20.MAVLink(None, srcSystem=42, srcComponent=191)
    sig = inspect.signature(m.vision_position_estimate_encode)
    print(f"v20.common.encode签名: {sig}")
    msg = m.vision_position_estimate_encode(0, 1.0, 2.0, 3.0, 0, 0, 0, [0.1]*21, 0)
    buf = msg.pack(m)
    print(f"9参数帧长度: {len(buf)}")
    print(f"hex前20: {buf[:20].hex()}")
    print(f"fieldnames: {msg.get_fieldnames()}")
except Exception as e:
    print(f"v20.common失败: {e}")

# 方案2: mavutil连接时指定dialect
try:
    from pymavlink import mavutil
    m2 = mavutil.mavlink_connection('udpout:127.0.0.1:14552', dialect='v20.common')
    print(f"\nmavutil dialect=v20.common连接成功")
    sig2 = inspect.signature(m2.mav.vision_position_estimate_encode)
    print(f"encode签名: {sig2}")
    msg2 = m2.mav.vision_position_estimate_encode(0, 1.0, 2.0, 3.0, 0, 0, 0, [0.1]*21, 0)
    print(f"帧长度: {len(msg2.pack(m2.mav))}")
except Exception as e:
    print(f"mavutil dialect方案失败: {e}")
