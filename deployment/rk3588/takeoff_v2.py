#!/usr/bin/env python3
"""
E2E-RL Takeoff Test v2 - Direct position control
Uses SET_POSITION_TARGET_LOCAL_NED instead of mode switching.
More compatible with ArduPilot firmwares.
"""
import sys
import time
import math
from pymavlink import mavutil

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 921600
TAKEOFF_HEIGHT = 0.8  # meters
HOVER_TIME = 3.0      # seconds

def connect():
    print(f"[CONNECT] {SERIAL_PORT} @ {BAUD_RATE}")
    m = mavutil.mavlink_connection(SERIAL_PORT, baud=BAUD_RATE)
    m.wait_heartbeat(timeout=5)
    hb = m.messages.get("HEARTBEAT")
    print(f"  Connected: sys={m.target_system} type={hb.type} autopilot={hb.autopilot}")
    print(f"  Mode: custom={hb.custom_mode:#010x} base={hb.base_mode:#04x}")
    return m

def get_state(m):
    pos = None
    att = None
    for _ in range(30):
        msg = m.recv_match(blocking=True, timeout=0.5)
        if msg:
            if msg.get_type() == "LOCAL_POSITION_NED":
                pos = msg
            elif msg.get_type() == "ATTITUDE":
                att = msg
            if pos and att:
                break
    return pos, att

def arm(m):
    print("[ARM] Arming...")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        1, 0, 0, 0, 0, 0, 0
    )
    for _ in range(30):
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=0.5)
        if hb and (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
            print("  ARMED!")
            return True
    print("  FAILED to arm")
    return False

def send_position_target(m, x, y, z):
    """Send position target in local NED frame (z=down)"""
    m.mav.set_position_target_local_ned_send(
        0,  # time_boot_ms
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b0000110111111000,  # type_mask: position only
        x, y, z,  # x, y, z positions (z is down)
        0, 0, 0,  # velocities
        0, 0, 0,  # accelerations
        0, 0      # yaw, yaw_rate
    )

def takeoff_direct(m, height):
    """Take off by sending position targets"""
    print(f"[TAKEOFF] Climbing to {height}m...")
    start = time.time()
    reached = False
    while time.time() - start < 15:
        # Send target repeatedly
        send_position_target(m, 0, 0, -height)  # z=-height (NED down)
        
        pos, att = get_state(m)
        if pos:
            alt = -pos.z
            print(f"  Alt: {alt:.2f}m", end="\r")
            if alt >= height * 0.9 and not reached:
                reached = True
                print(f"\n  Reached {height}m!")
                return True
        time.sleep(0.2)
    print(f"\n  Takeoff timeout")
    return reached

def hover(m, duration):
    print(f"\n[HOVER] Holding position for {duration}s...")
    start = time.time()
    while time.time() - start < duration:
        send_position_target(m, 0, 0, -TAKEOFF_HEIGHT)
        pos, att = get_state(m)
        if pos and att:
            alt = -pos.z
            print(f"  t={time.time()-start:.1f}s alt={alt:.2f}m "
                  f"r={math.degrees(att.roll):.1f} p={math.degrees(att.pitch):.1f}", end="\r")
        time.sleep(0.2)
    print()

def land(m):
    print("[LAND] Landing...")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND, 0,
        0, 0, 0, 0, 0, 0, 0
    )
    start = time.time()
    while time.time() - start < 15:
        pos, _ = get_state(m)
        if pos:
            alt = -pos.z
            print(f"  Alt: {alt:.2f}m", end="\r")
            if alt < 0.1:
                print("\n  Landed!")
                return True
        time.sleep(0.2)
    print("\n  Landing timeout")
    return False

def disarm(m):
    print("[DISARM] Disarming...")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
        0, 0, 0, 0, 0, 0, 0
    )
    time.sleep(1)
    print("  Disarmed")

def main():
    print("=" * 60)
    print("E2E-RL Takeoff Test v2 (Direct Position Control)")
    print("=" * 60)
    
    m = connect()
    
    # Get initial state
    pos, att = get_state(m)
    if pos:
        print(f"  Initial: x={pos.x:.2f} y={pos.y:.2f} z={-pos.z:.2f}m")
    if att:
        print(f"  Attitude: r={math.degrees(att.roll):.1f} p={math.degrees(att.pitch):.1f} y={math.degrees(att.yaw):.1f}")
    
    try:
        # Arm
        if not arm(m):
            print("[ABORT] Cannot arm")
            return
        
        # Take off using position targets
        if not takeoff_direct(m, TAKEOFF_HEIGHT):
            print("[WARN] May not have reached target, proceeding to land")
        
        # Hover
        hover(m, HOVER_TIME)
        
        # Land
        land(m)
        disarm(m)
        
        print("\n" + "=" * 60)
        print("TAKEOFF TEST COMPLETE")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n[INTERRUPT] Emergency landing...")
        land(m)
        disarm(m)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        try:
            land(m)
            disarm(m)
        except:
            pass
    finally:
        m.close()

if __name__ == "__main__":
    main()
