#!/usr/bin/env python3
"""Diagnose flight controller firmware and mode support"""
from pymavlink import mavutil
import math, time

m = mavutil.mavlink_connection("/dev/ttyACM0", baud=921600)
m.wait_heartbeat(timeout=5)

hb = m.messages.get("HEARTBEAT")
print(f"HEARTBEAT:")
print(f"  type: {hb.type}")
print(f"  autopilot: {hb.autopilot}")
print(f"  base_mode: {hb.base_mode:#04x}")
print(f"  custom_mode: {hb.custom_mode} ({hb.custom_mode:#010x})")
print(f"  system_status: {hb.system_status}")
print(f"  flightmode (pymavlink parsed): {m.flightmode}")

# Request AUTOPILOT_VERSION
print("\nRequesting AUTOPILOT_VERSION...")
m.mav.command_long_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,
    0, 148, 0, 0, 0, 0, 0, 0  # 148 = AUTOPILOT_VERSION
)
for _ in range(10):
    v = m.recv_match(type="AUTOPILOT_VERSION", blocking=True, timeout=1)
    if v:
        print(f"  Vendor: {v.vendor_id} Product: {v.product_id}")
        print(f"  Firmware: {v.flight_sw_version:#010x}")
        print(f"  Middleware: {v.middleware_sw_version:#010x}")
        print(f"  OS: {v.os_sw_version:#010x}")
        print(f"  Board: {v.board_version}")
        print(f"  Flight SW: {v.flight_custom_version.decode('ascii', errors='replace')}")
        print(f"  Middleware SW: {v.middleware_custom_version.decode('ascii', errors='replace')}")
        print(f"  OS SW: {v.os_custom_version.decode('ascii', errors='replace')}")
        break

# Try to list available modes via PARAM
print("\nReading FLTMODE1 parameter...")
m.mav.param_request_read_send(m.target_system, m.target_component, b"FLTMODE1", -1)
for _ in range(10):
    p = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
    if p and p.param_id.decode().startswith("FLTMODE"):
        print(f"  {p.param_id.decode()} = {p.param_value}")
        if p.param_id.decode() == "FLTMODE1":
            break

# Check ARMING_CHECK parameter
print("\nReading ARMING_CHECK...")
m.mav.param_request_read_send(m.target_system, m.target_component, b"ARMING_CHECK", -1)
for _ in range(10):
    p = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
    if p and p.param_id == b"ARMING_CHECK":
        print(f"  ARMING_CHECK = {p.param_value}")
        break

# Try setting GUIDED mode with different approaches
print("\nTrying GUIDED mode (approach 1: standard)...")
m.mav.command_long_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
    0, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 0, 0, 0, 0, 0
)
time.sleep(1)
hb2 = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
if hb2:
    print(f"  Result: custom_mode={hb2.custom_mode} flightmode={m.flightmode}")

print("\nTrying mode 4 (approach 2: MAV_MODE_FLAG_GUIDED)...")
m.mav.command_long_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
    0, mavutil.mavlink.MAV_MODE_FLAG_GUIDED_ENABLED | mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4, 0, 0, 0, 0, 0
)
time.sleep(1)
hb3 = m.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
if hb3:
    print(f"  Result: custom_mode={hb3.custom_mode} flightmode={m.flightmode}")

# Check STATUSTEXT for errors
print("\nRecent STATUSTEXT messages:")
for _ in range(5):
    s = m.recv_match(type="STATUSTEXT", blocking=True, timeout=0.5)
    if s:
        print(f"  [{s.severity}] {s.text.decode('ascii', errors='replace')}")

m.close()
print("\nDIAGNOSTIC COMPLETE")
