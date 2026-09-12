#!/usr/bin/env python3
from pymavlink import mavutil

m = mavutil.mavlink_connection('udpout:127.0.0.1:14551')
msg = m.mav.vision_position_estimate_encode(0, 0, 0, 0, 0, 0, 0)
print('crc_extra:', msg.crc_extra)
print('msgid:', msg.get_msgId())
print('fieldnames:', msg.get_fieldnames())
