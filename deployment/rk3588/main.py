#!/usr/bin/env python3
"""
E2E-RL Drone Flight Controller with Foxglove Visualization.

Hardware:
  - RealSense D430 depth camera (USB 3.0)
  - MicoAir743AIO flight controller (USB /dev/ttyACM0, 921600 baud, ArduPilot)
  - RK3588 onboard computer

Usage:
  python3 main.py --mode ground    # Ground test (no arming, no takeoff)
  python3 main.py --mode flight    # Full flight (TAKEOFF -> ATTACK -> RETURN)
  python3 main.py --mode policy    # Policy inference only, send to FC
  python3 main.py --foxglove-port 8765

Foxglove Studio connection: ws://<orange-pi-ip>:8765
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# Add project to path
sys.path.insert(0, str(Path(__file__).parent / "repo"))

from deployment.rk3588.inference import RK3588Policy


# ============================================================================
# Data structures
# ============================================================================

@dataclass
class DroneState:
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3))
    vel: np.ndarray = field(default_factory=lambda: np.zeros(3))
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    armed: bool = False
    mode: str = "UNKNOWN"
    battery: float = 0.0
    last_update: float = 0.0


@dataclass
class Target:
    pos: np.ndarray = field(default_factory=lambda: np.array([5.0, 0.0, 1.5]))
    detected: bool = False


# ============================================================================
# RealSense Depth Camera
# ============================================================================

class DepthCamera:
    """RealSense D430 depth camera wrapper."""

    def __init__(self, width=640, height=480, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.pipeline = None
        self.align = None
        self._connect()

    def _connect(self):
        import pyrealsense2 as rs
        self.rs = rs
        import pyrealsense2 as rs
        # D430 known-good: 1280x720@30, 848x480@30, 640x480@30
        for w, h, fps in [(1280, 720, 30), (848, 480, 30),
                          (640, 480, 30), (640, 480, 15), (480, 270, 30)]:
            for attempt in range(3):
                try:
                    config = rs.config()
                    config.enable_stream(rs.stream.depth, w, h, rs.format.z16, fps)
                    self.pipeline = rs.pipeline()
                    self.pipeline.start(config)
                    self.width, self.height, self.fps = w, h, fps
                    print(f"[Camera] RealSense D430 started: {w}x{h}@{fps}fps")
                    return
                except Exception as e:
                    try:
                        self.pipeline.stop()
                    except Exception:
                        pass
                    time.sleep(0.5)
        raise RuntimeError("Failed to start RealSense D430 after all retries")

    def get_depth(self) -> Optional[np.ndarray]:
        """Get depth frame in meters (float32, HxW)."""
        try:
            frames = self.pipeline.wait_for_frames(2000)
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                return None
            data = np.asanyarray(depth_frame.get_data(), dtype=np.float32)
            return data / 1000.0  # mm -> meters
        except Exception as e:
            print(f"[Camera] Error: {e}")
            return None

    def stop(self):
        if self.pipeline:
            self.pipeline.stop()
            print("[Camera] Stopped")


# ============================================================================
# Flight Controller (MAVLink / ArduPilot)
# ============================================================================

class FlightController:
    """MAVLink interface to ArduPilot flight controller."""

    def __init__(self, device="/dev/ttyACM0", baud=921600):
        from pymavlink import mavutil
        self.mavutil = mavutil
        self._device = device
        self._baud = baud
        self.master = mavutil.mavlink_connection(device, baud=baud)
        print(f"[FC] Connecting to {device} @ {baud}...")
        hb = self.master.wait_heartbeat(timeout=10)
        if not hb:
            raise RuntimeError("No heartbeat from flight controller")
        print(f"[FC] Connected: sys={self.master.target_system} "
              f"comp={self.master.target_component}")

        # Request data streams
        self.master.mav.request_data_stream_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL, 30, 1)

        self.state = DroneState()
        self._read_thread_running = True
        self._last_msg_time = time.time()

    def update(self, timeout=0.1):
        """Non-blocking read of latest MAVLink messages."""
        try:
            end = time.time() + timeout
            while time.time() < end:
                msg = self.master.recv_match(blocking=False)
                if msg is None:
                    break
                mtype = msg.get_type()
                if mtype == "ATTITUDE":
                    self.state.roll = msg.roll
                    self.state.pitch = msg.pitch
                    self.state.yaw = msg.yaw
                    self.state.last_update = time.time()
                elif mtype == "LOCAL_POSITION_NED":
                    self.state.pos = np.array([msg.x, msg.y, -msg.z])
                    self.state.vel = np.array([msg.vx, msg.vy, -msg.vz])
                elif mtype == "HEARTBEAT":
                    self.state.armed = bool(msg.base_mode &
                                            self.mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    cm = msg.custom_mode
                    modes = {0: "STABILIZE", 1: "ACRO", 2: "ALT_HOLD", 3: "AUTO",
                             4: "GUIDED", 5: "LOITER", 6: "RTL", 7: "CIRCLE",
                             9: "LAND", 16: "POSHOLD", 17: "BRAKE", 21: "AUTOTUNE"}
                    self.state.mode = modes.get(cm, f"MODE_{cm}")
                elif mtype == "SYS_STATUS":
                    self.state.battery = msg.voltage_battery / 1000.0
        except Exception as e:
            # Serial error - try to reconnect
            print(f"[FC] Serial error: {e}, attempting reconnect...")
            try:
                self.master.close()
            except Exception:
                pass
            time.sleep(1)
            try:
                self.master = self.mavutil.mavlink_connection(
                    self._device, baud=self._baud)
                self.master.wait_heartbeat(timeout=5)
                print("[FC] Reconnected")
            except Exception as e2:
                print(f"[FC] Reconnect failed: {e2}")

    def arm(self):
        """Arm the drone."""
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            self.mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            1, 0, 0, 0, 0, 0, 0)
        print("[FC] ARM command sent")

    def disarm(self):
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            self.mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            0, 0, 0, 0, 0, 0, 0)
        print("[FC] DISARM command sent")

    def set_mode(self, mode: str):
        """Set flight mode (GUIDED, LOITER, RTL, LAND)."""
        mode_map = {"GUIDED": 4, "LOITER": 5, "RTL": 6, "LAND": 9, "ALT_HOLD": 2}
        if mode not in mode_map:
            print(f"[FC] Unknown mode: {mode}")
            return
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            self.mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
            self.mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_map[mode], 0, 0, 0, 0, 0)
        print(f"[FC] Mode -> {mode}")

    def send_velocity(self, vx: float, vy: float, vz: float, yaw_rate: float = 0):
        """Send velocity target in body frame (GUIDED mode)."""
        self.master.mav.set_position_target_local_ned_send(
            0, self.master.target_system, self.master.target_component,
            self.mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
            0b0000011111000111,  # velocity + yaw_rate
            0, 0, 0,  # pos (ignored)
            vx, vy, vz,  # velocity (NED body frame)
            0, 0, 0,  # accel (ignored)
            0, yaw_rate)

    def send_accel(self, ax: float, ay: float, az: float, yaw_rate: float = 0):
        """Send acceleration target (GUIDED mode).
        Note: ArduPilot GUIDED supports velocity/position, accel needs special handling.
        We convert accel to velocity via PID for now.
        """
        # Simple integration: velocity += accel * dt (dt ~ 0.033s)
        dt = 0.033
        self._target_vel = getattr(self, '_target_vel', np.zeros(3))
        self._target_vel += np.array([ax, ay, -az]) * dt  # ENU->NED z flip
        self._target_vel = np.clip(self._target_vel, -5, 5)
        self.send_velocity(self._target_vel[0], self._target_vel[1],
                           self._target_vel[2], yaw_rate)

    def takeoff(self, alt: float = 1.5):
        """Take off to specified altitude (meters)."""
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            self.mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, alt)
        print(f"[FC] Takeoff -> {alt}m")

    def land(self):
        self.set_mode("LAND")
        print("[FC] Landing")

    def close(self):
        self._read_thread_running = False
        self.master.close()


# ============================================================================
# Foxglove WebSocket Server
# ============================================================================

class FoxgloveServer:
    """Foxglove WebSocket server for live visualization."""

    def __init__(self, host="0.0.0.0", port=8766):
        from foxglove_websocket.server import FoxgloveServer as FGS
        from foxglove_websocket.types import ChannelWithoutId
        self.FGS = FGS
        self.ChannelWithoutId = ChannelWithoutId
        self.host = host
        self.port = port
        self.server = None
        self.channels = {}

    async def start(self):
        self.server = self.FGS(self.host, self.port, "E2E-RL Drone")
        self.server.start()  # synchronous

        # Register channels (TypedDict: topic, schema_name, encoding)
        for name, topic, schema in [
            ("depth", "/drone/depth", "sensor_msgs/Image"),
            ("pose", "/drone/pose", "geometry_msgs/Pose"),
            ("velocity", "/drone/velocity", "geometry_msgs/Vector3"),
            ("target", "/drone/target", "geometry_msgs/Point"),
            ("policy_action", "/drone/policy_action", "geometry_msgs/Vector3"),
            ("status", "/drone/status", "std_msgs/String"),
            ("trajectory", "/drone/trajectory", "nav_msgs/Path"),
        ]:
            self.channels[name] = await self.server.add_channel(
                self.ChannelWithoutId(topic=topic, schema_name=schema, encoding="json")
            )

        print(f"[Foxglove] Server started on ws://{self.host}:{self.port}")
        print(f"[Foxglove] Connect: ws://<pi-ip>:{self.port}")

    async def send_depth(self, depth: np.ndarray, timestamp: float):
        import cv2
        depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
        depth_vis = (depth_vis * 255).astype(np.uint8)
        depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
        _, png_data = cv2.imencode('.png', depth_colored)
        msg = {
            "timestamp": timestamp,
            "width": int(depth.shape[1]),
            "height": int(depth.shape[0]),
            "encoding": "png",
            "data": png_data.tobytes().hex(),
        }
        await self.server.send_message(self.channels["depth"], timestamp,
                                       json.dumps(msg).encode())

    async def send_pose(self, pos: np.ndarray, roll: float, pitch: float,
                        yaw: float, timestamp: float):
        import math
        qx = math.sin(roll/2)*math.cos(pitch/2)*math.cos(yaw/2) - math.cos(roll/2)*math.sin(pitch/2)*math.sin(yaw/2)
        qy = math.cos(roll/2)*math.sin(pitch/2)*math.cos(yaw/2) + math.sin(roll/2)*math.cos(pitch/2)*math.sin(yaw/2)
        qz = math.cos(roll/2)*math.cos(pitch/2)*math.sin(yaw/2) - math.sin(roll/2)*math.sin(pitch/2)*math.cos(yaw/2)
        qw = math.cos(roll/2)*math.cos(pitch/2)*math.cos(yaw/2) + math.sin(roll/2)*math.sin(pitch/2)*math.sin(yaw/2)
        msg = {
            "position": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
            "orientation": {"x": qx, "y": qy, "z": qz, "w": qw},
        }
        await self.server.send_message(self.channels["pose"], timestamp,
                                       json.dumps(msg).encode())

    async def send_vector3(self, channel_id: int, vec: np.ndarray, timestamp: float):
        msg = {"x": float(vec[0]), "y": float(vec[1]), "z": float(vec[2])}
        await self.server.send_message(channel_id, timestamp,
                                       json.dumps(msg).encode())

    async def send_status(self, text: str, timestamp: float):
        msg = {"data": text}
        await self.server.send_message(self.channels["status"], timestamp,
                                       json.dumps(msg).encode())

    async def send_trajectory(self, points: list, timestamp: float):
        msg = {
            "poses": [{"position": {"x": float(p[0]), "y": float(p[1]), "z": float(p[2])}}
                      for p in points[-500:]]
        }
        await self.server.send_message(self.channels["trajectory"], timestamp,
                                       json.dumps(msg).encode())

    async def stop(self):
        if self.server:
            self.server.close()  # synchronous
            print("[Foxglove] Server stopped")


# ============================================================================
# Main Flight Program
# ============================================================================

class DroneApp:
    def __init__(self, args):
        self.args = args
        self.running = True
        self.mode = "IDLE"  # IDLE, TAKEOFF, ATTACK, RETURN, LAND
        self.trajectory = []
        self.policy = None
        self.camera = None
        self.fc = None
        self.foxglove = None
        self.target = Target()
        self.hit_detected = False
        self.episode_start = 0

    def setup(self):
        """Initialize hardware and policy."""
        # Depth camera
        if self.args.sim_depth:
            print("[Camera] Using SIMULATED depth (no camera)")
            self.camera = None
            self._sim_depth_frame = 0
        elif not self.args.no_camera:
            try:
                self.camera = DepthCamera(width=640, height=480, fps=30)
            except Exception as e:
                print(f"[Camera] Failed to start RealSense: {e}")
                print("[Camera] Falling back to simulated depth")
                self.camera = None
                self._sim_depth_frame = 0

        # Flight controller
        if not self.args.no_fc:
            try:
                self.fc = FlightController(device=self.args.device, baud=self.args.baud)
            except Exception as e:
                print(f"[FC] Failed to connect: {e}")
                print("[FC] Falling back to simulated state")
                self.fc = None
                self._sim_state = DroneState()
                self._sim_pos = np.array([0.0, 0.0, 0.0])
                self._sim_vel = np.array([0.0, 0.0, 0.0])
                self._sim_yaw = 0.0

        # Policy
        model_path = str(Path(__file__).parent / "repo" / "deployment" / "onnx" / "policy.onnx")
        self.policy = RK3588Policy(model_path, use_npu=False)
        self.policy.reset()
        print("[Policy] Loaded")

    async def run(self):
        """Main loop."""
        # Start Foxglove
        self.foxglove = FoxgloveServer(port=self.args.foxglove_port)
        await self.foxglove.start()

        # Setup hardware
        self.setup()

        print(f"\n{'='*60}")
        print(f"E2E-RL Drone - Mode: {self.args.mode}")
        print(f"Foxglove: ws://0.0.0.0:{self.args.foxglove_port}")
        print(f"Press Ctrl+C to stop")
        print(f"{'='*60}\n")

        if self.args.mode == "ground":
            await self._ground_test()
        elif self.args.mode == "flight":
            await self._full_flight()
        elif self.args.mode == "policy":
            await self._policy_only()

        # Cleanup
        await self.shutdown()

    async def _ground_test(self):
        """Ground test: read sensors, run policy, visualize, but don't arm/takeoff."""
        print("[GROUND TEST] Reading sensors and running policy (no arming)")
        count = 0
        while self.running:
            t = time.time()
            timestamp = int(t * 1e9)

            # Update FC state
            if self.fc:
                self.fc.update(timeout=0.01)
                state = self.fc.state
            else:
                # Simulated drone state (slow drift for visualization)
                self._sim_pos += self._sim_vel * 0.033
                self._sim_yaw += 0.001
                state = DroneState(pos=self._sim_pos.copy(),
                                   vel=self._sim_vel.copy(),
                                   yaw=self._sim_yaw,
                                   mode="SIM")

            # Get depth
            depth = None
            if self.camera:
                depth = self.camera.get_depth()
            elif self.args.sim_depth:
                # Simulated depth: gradient + noise (for testing without camera)
                self._sim_depth_frame += 1
                h, w = 480, 640
                y, x = np.mgrid[0:h, 0:w]
                depth = 3.0 + 0.01 * x + 0.005 * np.sin(self._sim_depth_frame * 0.1)
                depth = depth.astype(np.float32)
                depth += np.random.randn(h, w).astype(np.float32) * 0.1

            # Run policy if depth available
            action = None
            if depth is not None and self.policy:
                action = self.policy.infer(
                    depth, state.pos, state.vel, state.yaw, self.target.pos)

            # Record trajectory
            self.trajectory.append(state.pos.copy())
            if len(self.trajectory) > 1000:
                self.trajectory.pop(0)

            # Foxglove updates (at ~10Hz to avoid overload)
            if count % 3 == 0:
                if depth is not None:
                    await self.foxglove.send_depth(depth, timestamp)
                await self.foxglove.send_pose(
                    state.pos, state.roll, state.pitch, state.yaw, timestamp)
                await self.foxglove.send_vector3(
                    self.foxglove.channels["velocity"], state.vel, timestamp)
                await self.foxglove.send_vector3(
                    self.foxglove.channels["target"], self.target.pos, timestamp)
                if action:
                    await self.foxglove.send_vector3(
                        self.foxglove.channels["policy_action"],
                        action["accel"], timestamp)
                await self.foxglove.send_trajectory(self.trajectory, timestamp)

                status = (f"MODE=GROUND | armed={state.armed} fc_mode={state.mode} | "
                          f"pos=({state.pos[0]:.2f},{state.pos[1]:.2f},{state.pos[2]:.2f}) | "
                          f"yaw={state.yaw:.2f} | batt={state.battery:.1f}V | "
                          f"depth={'OK' if depth is not None else 'NONE'} | "
                          f"policy_lat={action['latency_ms']:.2f}ms" if action else "N/A")
                await self.foxglove.send_status(status, timestamp)

            # Console output at 1Hz
            if count % 30 == 0:
                print(f"[{count:5d}] pos=({state.pos[0]:.2f},{state.pos[1]:.2f},{state.pos[2]:.2f}) "
                      f"yaw={state.yaw:.2f} armed={state.armed} mode={state.mode} "
                      f"depth={'OK' if depth is not None else 'NONE'} "
                      f"policy={action['latency_ms']:.1f}ms" if action else "")

            count += 1
            await asyncio.sleep(0.033)  # ~30Hz

    async def _policy_only(self):
        """Policy inference + send velocity to FC (GUIDED mode, no takeoff)."""
        print("[POLICY MODE] Running policy and sending velocity to FC")
        print("  Make sure FC is in GUIDED mode and ARMED")
        print("  Drone should be at safe altitude (manual takeoff first)")
        count = 0
        while self.running:
            t = time.time()
            timestamp = int(t * 1e9)

            if self.fc:
                self.fc.update(timeout=0.01)
                state = self.fc.state
            else:
                state = DroneState()

            depth = self.camera.get_depth() if self.camera else None

            if depth is not None and self.policy and self.fc and state.armed:
                action = self.policy.infer(
                    depth, state.pos, state.vel, state.yaw, self.target.pos)
                # Convert accel to velocity command
                self.fc.send_accel(
                    action["accel"][0], action["accel"][1],
                    action["accel"][2], action.get("yaw_rate", 0))
            else:
                action = None

            # Foxglove
            if count % 3 == 0:
                if depth is not None:
                    await self.foxglove.send_depth(depth, timestamp)
                await self.foxglove.send_pose(
                    state.pos, state.roll, state.pitch, state.yaw, timestamp)
                if action:
                    await self.foxglove.send_vector3(
                        self.foxglove.channels["policy_action"],
                        action["accel"], timestamp)
                self.trajectory.append(state.pos.copy())
                await self.foxglove.send_trajectory(self.trajectory, timestamp)

            count += 1
            await asyncio.sleep(0.033)

    async def _full_flight(self):
        """Full autonomous flight: TAKEOFF -> ATTACK -> RETURN -> LAND."""
        print("[FLIGHT MODE] Full autonomous mission")
        print("  WARNING: This will ARM and TAKEOFF the drone!")

        # Wait for FC ready
        if self.fc:
            for _ in range(30):
                self.fc.update(timeout=0.1)
                if self.fc.state.battery > 0:
                    break
            print(f"[FLIGHT] Battery: {self.fc.state.battery:.1f}V")

            # Set GUIDED mode and arm
            self.fc.set_mode("GUIDED")
            await asyncio.sleep(1)
            self.fc.arm()
            await asyncio.sleep(2)

            # Takeoff
            self.mode = "TAKEOFF"
            self.fc.takeoff(self.args.takeoff_alt)
            self.episode_start = time.time()

            # Wait for takeoff
            for _ in range(100):
                self.fc.update(timeout=0.05)
                if self.fc.state.pos[2] >= self.args.takeoff_alt * 0.9:
                    print(f"[FLIGHT] Reached altitude {self.fc.state.pos[2]:.2f}m")
                    break
                await asyncio.sleep(0.1)

            # ATTACK phase
            self.mode = "ATTACK"
            self.policy.reset()
            print("[FLIGHT] ATTACK phase - policy active")

            attack_start = time.time()
            while self.running and time.time() - attack_start < self.args.attack_timeout:
                t = time.time()
                timestamp = int(t * 1e9)

                self.fc.update(timeout=0.01)
                state = self.fc.state
                depth = self.camera.get_depth() if self.camera else None

                if depth is not None:
                    action = self.policy.infer(
                        depth, state.pos, state.vel, state.yaw, self.target.pos)
                    self.fc.send_accel(
                        action["accel"][0], action["accel"][1],
                        action["accel"][2], action.get("yaw_rate", 0))

                    # Check hit (distance < threshold)
                    dist = np.linalg.norm(state.pos - self.target.pos)
                    if dist < 0.5:
                        self.hit_detected = True
                        print(f"[FLIGHT] TARGET HIT! dist={dist:.2f}m")
                        break

                # Foxglove
                if depth is not None:
                    await self.foxglove.send_depth(depth, timestamp)
                await self.foxglove.send_pose(
                    state.pos, state.roll, state.pitch, state.yaw, timestamp)
                self.trajectory.append(state.pos.copy())
                await self.foxglove.send_trajectory(self.trajectory, timestamp)

                await asyncio.sleep(0.033)

            # RETURN phase
            self.mode = "RETURN"
            print("[FLIGHT] RETURN to home")
            self.fc.set_mode("RTL")
            await asyncio.sleep(5)

            # LAND
            self.mode = "LAND"
            self.fc.land()

        await asyncio.sleep(1)

    async def shutdown(self):
        print("\n[Shutdown] Cleaning up...")
        self.running = False
        if self.fc:
            if self.fc.state.armed and self.mode != "LAND":
                self.fc.set_mode("LOITER")
            self.fc.close()
        if self.camera:
            self.camera.stop()
        if self.foxglove:
            await self.foxglove.stop()
        print("[Shutdown] Done")


def main():
    parser = argparse.ArgumentParser(description="E2E-RL Drone Flight Controller")
    parser.add_argument("--mode", choices=["ground", "flight", "policy"],
                        default="ground", help="Operation mode")
    parser.add_argument("--device", default="/dev/ttyACM0", help="FC serial device")
    parser.add_argument("--baud", type=int, default=921600, help="FC baud rate")
    parser.add_argument("--foxglove-port", type=int, default=8766, help="Foxglove WS port")
    parser.add_argument("--takeoff-alt", type=float, default=1.5, help="Takeoff altitude")
    parser.add_argument("--attack-timeout", type=float, default=30, help="Attack phase timeout")
    parser.add_argument("--no-camera", action="store_true", help="Disable camera")
    parser.add_argument("--sim-depth", action="store_true", help="Use simulated depth")
    parser.add_argument("--no-fc", action="store_true", help="Disable flight controller")
    args = parser.parse_args()

    app = DroneApp(args)

    def signal_handler(sig, frame):
        print("\n[Signal] Ctrl+C received, shutting down...")
        app.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    asyncio.run(app.run())


if __name__ == "__main__":
    main()
