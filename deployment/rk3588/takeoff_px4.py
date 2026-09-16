#!/usr/bin/env python3
"""
E2E-RL PX4 Takeoff Test
PX4 workflow: send setpoints -> OFFBOARD mode -> ARM -> takeoff -> hover -> land
"""
import sys
import time
import math
import threading
from pymavlink import mavutil

SERIAL_PORT = "/dev/ttyACM0"
BAUD_RATE = 921600
TAKEOFF_HEIGHT = 0.8  # meters
HOVER_TIME = 3.0      # seconds

# PX4 custom mode encoding: (main_mode << 16) | (sub_mode << 8)
PX4_MODE_OFFBOARD = 6 << 16
PX4_MODE_AUTO_LAND = (4 << 16) | (5 << 8)  # AUTO.LAND

class SetpointSender:
    """Background thread to continuously send position setpoints (>2Hz required by PX4)"""
    def __init__(self, master):
        self.master = master
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0  # NED: negative = up
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def set_target(self, x, y, z):
        self.target_x = x
        self.target_y = y
        self.target_z = z  # NED down: negative = up

    def _loop(self):
        while self.running:
            self.master.mav.set_position_target_local_ned_send(
                0,
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                0b0000110111111000,  # position only
                self.target_x, self.target_y, self.target_z,
                0, 0, 0,  # velocities
                0, 0, 0,  # accelerations
                0, 0      # yaw, yaw_rate
            )
            time.sleep(0.1)  # 10Hz

def connect():
    print(f"[CONNECT] {SERIAL_PORT} @ {BAUD_RATE}")
    m = mavutil.mavlink_connection(SERIAL_PORT, baud=BAUD_RATE)
    m.wait_heartbeat(timeout=5)
    hb = m.messages.get("HEARTBEAT")
    print(f"  PX4 Connected: sys={m.target_system}")
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

def set_mode_offboard(m):
    print("[MODE] Switching to OFFBOARD...")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        PX4_MODE_OFFBOARD, 0, 0, 0, 0, 0
    )
    for _ in range(20):
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=0.5)
        if hb and hb.custom_mode == PX4_MODE_OFFBOARD:
            print("  OFFBOARD mode active!")
            return True
        time.sleep(0.2)
    print("  WARNING: mode may not have switched, continuing...")
    return True

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
            print("  ARMED! Motors spinning!")
            return True
        time.sleep(0.2)
    print("  FAILED to arm")
    return False

def wait_altitude(m, target_alt, timeout=15):
    print(f"[CLIMB] Waiting for altitude {target_alt}m...")
    start = time.time()
    while time.time() - start < timeout:
        pos, att = get_state(m)
        if pos:
            alt = -pos.z  # NED z is down
            print(f"  Alt: {alt:.2f}m", end="\r")
            if alt >= target_alt * 0.9:
                print(f"\n  Reached {target_alt}m!")
                return True
        time.sleep(0.2)
    print(f"\n  Timeout at {alt if pos else '?'}m")
    return False

def hover(m, sender, duration):
    print(f"\n[HOVER] Holding {TAKEOFF_HEIGHT}m for {duration}s...")
    start = time.time()
    while time.time() - start < duration:
        pos, att = get_state(m)
        if pos and att:
            alt = -pos.z
            print(f"  t={time.time()-start:.1f}s alt={alt:.2f}m "
                  f"r={math.degrees(att.roll):.1f} p={math.degrees(att.pitch):.1f}", end="\r")
        time.sleep(0.2)
    print()

def land(m):
    print("[LAND] Switching to AUTO.LAND...")
    m.mav.command_long_send(
        m.target_system, m.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        PX4_MODE_AUTO_LAND, 0, 0, 0, 0, 0
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
    print("E2E-RL PX4 Takeoff Test")
    print("=" * 60)

    m = connect()

    # Get initial state
    pos, att = get_state(m)
    if pos:
        print(f"  Initial: x={pos.x:.2f} y={pos.y:.2f} z={-pos.z:.2f}m")
    if att:
        print(f"  Attitude: r={math.degrees(att.roll):.1f} p={math.degrees(att.pitch):.1f} y={math.degrees(att.yaw):.1f}")

    # Start setpoint sender BEFORE switching mode (PX4 requires this)
    sender = SetpointSender(m)
    sender.set_target(0, 0, -TAKEOFF_HEIGHT)  # NED: -0.8 = 0.8m up
    sender.start()
    print("[SETPOINT] Sending position targets at 10Hz...")
    time.sleep(1)  # Let setpoints flow

    try:
        # Switch to OFFBOARD
        if not set_mode_offboard(m):
            print("[ABORT] Cannot enter OFFBOARD")
            sender.stop()
            return

        # Arm
        if not arm(m):
            print("[ABORT] Cannot arm")
            land(m)
            disarm(m)
            sender.stop()
            return

        # Wait for takeoff
        wait_altitude(m, TAKEOFF_HEIGHT)

        # Hover
        hover(m, sender, HOVER_TIME)

        # Land
        land(m)
        disarm(m)

        print("\n" + "=" * 60)
        print("PX4 TAKEOFF TEST COMPLETE!")
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
        sender.stop()
        m.close()

if __name__ == "__main__":
    main()
