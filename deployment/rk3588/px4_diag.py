#!/usr/bin/env python3
"""Check PX4 arming failure reasons and status messages"""
from pymavlink import mavutil
import time

m = mavutil.mavlink_connection("/dev/ttyACM0", baud=921600)
m.wait_heartbeat(timeout=5)

# Request all params
print("Requesting parameters...")
m.mav.param_request_list_send(m.target_system, m.target_component)

# Collect STATUSTEXT and PARAM_VALUE for 5 seconds
start = time.time()
status_texts = []
params = {}
while time.time() - start < 8:
    msg = m.recv_match(blocking=True, timeout=0.5)
    if msg:
        mt = msg.get_type()
        if mt == "STATUSTEXT":
            text = msg.text.decode('ascii', errors='replace')
            status_texts.append(f"[{msg.severity}] {text}")
            print(f"  STATUS: [{msg.severity}] {text}")
        elif mt == "PARAM_VALUE":
            pid = msg.param_id if isinstance(msg.param_id, str) else msg.param_id.decode('ascii', errors='replace')
            if any(k in pid.upper() for k in ['ARM', 'GPS', 'COM_', 'EKF2', 'SYS']):
                params[pid] = msg.param_value

print("\n=== Key Parameters ===")
for k in sorted(params.keys()):
    print(f"  {k} = {params[k]}")

# Try to read specific params
print("\n=== Arming-related params ===")
for param_name in ["COM_ARM_WITHOUT_GPS", "COM_ARM_MAG_STR", "COM_ARM_INAV", 
                   "EKF2_HGT_REF", "EKF2_AID_MASK", "SYS_USE_IO"]:
    m.mav.param_request_read_send(m.target_system, m.target_component, 
                                   param_name.encode(), -1)
    for _ in range(5):
        p = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
        if p:
            pid = p.param_id if isinstance(p.param_id, str) else p.param_id.decode()
            if pid == param_name:
                print(f"  {param_name} = {p.param_value}")
                break

# Check current mode and try to switch to POSCTL first
print("\n=== Current Mode ===")
hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
if hb:
    print(f"  custom_mode={hb.custom_mode:#010x} base_mode={hb.base_mode:#04x}")
    main_mode = (hb.custom_mode >> 16) & 0xFF
    sub_mode = (hb.custom_mode >> 8) & 0xFF
    print(f"  main_mode={main_mode} sub_mode={sub_mode}")
    px4_modes = {1:"MANUAL",2:"ALTCTL",3:"POSCTL",4:"AUTO",5:"ACRO",6:"OFFBOARD",7:"STABILIZED",8:"RATTITUDE"}
    print(f"  Mode: {px4_modes.get(main_mode, 'UNKNOWN')}")

m.close()
print("\nDIAGNOSTIC COMPLETE")
