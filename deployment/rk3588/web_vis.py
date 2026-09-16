#!/usr/bin/env python3
"""
E2E-RL Drone - Web Visualization Server

Simple HTTP server that serves:
- /          -> HTML dashboard (depth image + telemetry + charts)
- /depth.mjpg -> MJPEG stream of colorized depth
- /status     -> JSON telemetry (pose, velocity, policy action, etc.)

Run on Orange Pi 5: python3 web_vis.py [--port 8080]
Open in browser: http://192.168.1.215:8080
"""
import sys
import time
import json
import threading
import traceback
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import numpy as np

# ============================================================================
# Configuration
# ============================================================================
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_FPS = 30
TARGET_POS = np.array([3.0, 0.0, 1.0])
DEPTH_RANGE = (0.3, 24.0)  # meters

# Shared state (updated by camera/policy thread, read by HTTP thread)
state_lock = threading.Lock()
shared_state = {
    "depth_frame": None,       # np.ndarray HxW float32 (meters)
    "depth_colored": None,     # np.ndarray HxWx3 uint8 (JET colormap)
    "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
    "velocity": {"x": 0, "y": 0, "z": 0},
    "policy_action": {"ax": 0, "ay": 0, "az": 0},
    "target": {"x": 3.0, "y": 0.0, "z": 1.0},
    "status": "INIT",
    "fps": 0,
    "depth_valid_ratio": 0,
    "battery": 0,
    "armed": False,
    "fc_mode": "UNKNOWN",
    "trajectory": [],
    "frame_count": 0,
}

# ============================================================================
# HTML Dashboard
# ============================================================================
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>E2E-RL Drone Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #eee; font-family: 'Segoe UI', sans-serif; padding: 10px; }
  .header { text-align: center; padding: 10px; background: #16213e; border-radius: 8px; margin-bottom: 10px; }
  .header h1 { color: #e94560; font-size: 20px; }
  .header .status { color: #0f3460; font-size: 14px; margin-top: 4px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .panel { background: #16213e; border-radius: 8px; padding: 12px; }
  .panel h2 { color: #e94560; font-size: 14px; margin-bottom: 8px; border-bottom: 1px solid #0f3460; padding-bottom: 4px; }
  .depth-container { text-align: center; }
  .depth-container img { width: 100%; max-height: 400px; border-radius: 4px; background: #000; }
  .telemetry { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 13px; }
  .telemetry .item { background: #0f3460; padding: 6px 8px; border-radius: 4px; }
  .telemetry .label { color: #888; font-size: 11px; }
  .telemetry .value { color: #fff; font-size: 16px; font-weight: bold; }
  .bar-container { margin: 4px 0; }
  .bar-label { font-size: 11px; color: #888; display: flex; justify-content: space-between; }
  .bar-bg { background: #0f3460; height: 16px; border-radius: 3px; overflow: hidden; }
  .bar-fill { height: 100%; transition: width 0.1s; border-radius: 3px; }
  .bar-ax { background: #e94560; }
  .bar-ay { background: #f5a623; }
  .bar-az { background: #4ecdc4; }
  .status-text { font-size: 12px; color: #aaa; line-height: 1.6; }
  .trajectory-canvas { width: 100%; height: 200px; background: #0a0a1a; border-radius: 4px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: bold; }
  .badge-ok { background: #0f3460; color: #4ecdc4; }
  .badge-warn { background: #f5a623; color: #000; }
  .badge-err { background: #e94560; color: #fff; }
</style>
</head>
<body>
<div class="header">
  <h1>E2E-RL Drone Dashboard</h1>
  <div class="status" id="conn-status">Connecting...</div>
</div>
<div class="grid">
  <div class="panel">
    <h2>Depth Camera (RealSense D430)</h2>
    <div class="depth-container">
      <img src="/depth.mjpg" alt="Depth stream" onerror="this.style.opacity=0.3">
    </div>
    <div style="margin-top:8px; font-size:11px; color:#888;">
      暖色=近 | 冷色=远 | 范围 0.3-24m
    </div>
  </div>
  <div class="panel">
    <h2>Telemetry</h2>
    <div class="telemetry">
      <div class="item"><div class="label">Position X</div><div class="value" id="pos-x">0.00</div></div>
      <div class="item"><div class="label">Position Y</div><div class="value" id="pos-y">0.00</div></div>
      <div class="item"><div class="label">Position Z</div><div class="value" id="pos-z">0.00</div></div>
      <div class="item"><div class="label">Yaw</div><div class="value" id="yaw">0.0°</div></div>
      <div class="item"><div class="label">Velocity</div><div class="value" id="vel">0.00 m/s</div></div>
      <div class="item"><div class="label">FPS</div><div class="value" id="fps">0</div></div>
      <div class="item"><div class="label">Battery</div><div class="value" id="batt">0.0V</div></div>
      <div class="item"><div class="label">Depth Valid</div><div class="value" id="depth-valid">0%</div></div>
    </div>
    <div style="margin-top:10px;">
      <span class="badge badge-ok" id="armed-badge">DISARMED</span>
      <span class="badge badge-ok" id="mode-badge">UNKNOWN</span>
    </div>
  </div>
  <div class="panel">
    <h2>Policy Output (Acceleration)</h2>
    <div class="bar-container">
      <div class="bar-label"><span>AX (Forward)</span><span id="ax-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-ax" id="ax-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>AY (Right)</span><span id="ay-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-ay" id="ay-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>AZ (Up)</span><span id="az-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-az" id="az-bar" style="width:50%"></div></div>
    </div>
    <div style="margin-top:10px; font-size:11px; color:#888;">
      范围: ±10 m/s² | 中间=0
    </div>
  </div>
  <div class="panel">
    <h2>Trajectory (Top-Down)</h2>
    <canvas class="trajectory-canvas" id="traj-canvas"></canvas>
    <div style="margin-top:6px; font-size:11px; color:#888;">
      <span style="color:#e94560;">■</span> Drone | 
      <span style="color:#4ecdc4;">■</span> Target | 
      <span style="color:#f5a623;">■</span> Trail
    </div>
  </div>
</div>
<div class="panel" style="margin-top:10px;">
  <h2>Status</h2>
  <div class="status-text" id="status-text">Waiting for data...</div>
</div>

<script>
let trajPoints = [];
const MAX_TRAJ = 500;

async function updateStatus() {
  try {
    const resp = await fetch('/status');
    const s = await resp.json();
    document.getElementById('conn-status').textContent = 'Connected | ' + new Date().toLocaleTimeString();
    document.getElementById('conn-status').style.color = '#4ecdc4';

    document.getElementById('pos-x').textContent = s.pose.x.toFixed(2);
    document.getElementById('pos-y').textContent = s.pose.y.toFixed(2);
    document.getElementById('pos-z').textContent = s.pose.z.toFixed(2);
    document.getElementById('yaw').textContent = (s.pose.yaw * 180 / Math.PI).toFixed(1) + '°';
    const vel = Math.sqrt(s.velocity.x**2 + s.velocity.y**2 + s.velocity.z**2);
    document.getElementById('vel').textContent = vel.toFixed(2) + ' m/s';
    document.getElementById('fps').textContent = s.fps;
    document.getElementById('batt').textContent = s.battery.toFixed(1) + 'V';
    document.getElementById('depth-valid').textContent = (s.depth_valid_ratio * 100).toFixed(0) + '%';

    const armedBadge = document.getElementById('armed-badge');
    armedBadge.textContent = s.armed ? 'ARMED' : 'DISARMED';
    armedBadge.className = 'badge ' + (s.armed ? 'badge-warn' : 'badge-ok');
    document.getElementById('mode-badge').textContent = s.fc_mode;

    // Policy bars (center at 50%, range ±10)
    const ax = Math.max(-10, Math.min(10, s.policy_action.ax));
    const ay = Math.max(-10, Math.min(10, s.policy_action.ay));
    const az = Math.max(-10, Math.min(10, s.policy_action.az));
    document.getElementById('ax-val').textContent = ax.toFixed(2);
    document.getElementById('ay-val').textContent = ay.toFixed(2);
    document.getElementById('az-val').textContent = az.toFixed(2);
    document.getElementById('ax-bar').style.width = (50 + ax * 5) + '%';
    document.getElementById('ay-bar').style.width = (50 + ay * 5) + '%';
    document.getElementById('az-bar').style.width = (50 + az * 5) + '%';

    document.getElementById('status-text').textContent = s.status;

    // Trajectory
    trajPoints.push([s.pose.x, s.pose.y]);
    if (trajPoints.length > MAX_TRAJ) trajPoints.shift();
    drawTrajectory(s.target);
  } catch(e) {
    document.getElementById('conn-status').textContent = 'Disconnected: ' + e.message;
    document.getElementById('conn-status').style.color = '#e94560';
  }
}

function drawTrajectory(target) {
  const canvas = document.getElementById('traj-canvas');
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth;
  const h = canvas.height = canvas.offsetHeight;
  ctx.fillStyle = '#0a0a1a';
  ctx.fillRect(0, 0, w, h);

  if (trajPoints.length < 2) return;

  // Auto-scale
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  trajPoints.forEach(p => {
    minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]);
    minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]);
  });
  minX = Math.min(minX, target.x); maxX = Math.max(maxX, target.x);
  minY = Math.min(minY, target.y); maxY = Math.max(maxY, target.y);
  const range = Math.max(maxX - minX, maxY - minY, 1);
  const pad = 20;
  const scale = Math.min(w - 2*pad, h - 2*pad) / range;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const toPx = (x, y) => [pad + (x - cx + range/2) * scale, h - pad - (y - cy + range/2) * scale];

  // Grid
  ctx.strokeStyle = '#1a1a3e';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    ctx.beginPath();
    ctx.moveTo(pad + i * (w - 2*pad) / 4, pad);
    ctx.lineTo(pad + i * (w - 2*pad) / 4, h - pad);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(pad, pad + i * (h - 2*pad) / 4);
    ctx.lineTo(w - pad, pad + i * (h - 2*pad) / 4);
    ctx.stroke();
  }

  // Trail
  ctx.strokeStyle = '#f5a623';
  ctx.lineWidth = 2;
  ctx.beginPath();
  trajPoints.forEach((p, i) => {
    const [px, py] = toPx(p[0], p[1]);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  // Target
  const [tx, ty] = toPx(target.x, target.y);
  ctx.fillStyle = '#4ecdc4';
  ctx.beginPath();
  ctx.arc(tx, ty, 8, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.font = '10px sans-serif';
  ctx.fillText('TARGET', tx + 10, ty - 8);

  // Drone (latest point)
  const last = trajPoints[trajPoints.length - 1];
  const [dx, dy] = toPx(last[0], last[1]);
  ctx.fillStyle = '#e94560';
  ctx.beginPath();
  ctx.arc(dx, dy, 6, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillText('DRONE', dx + 10, dy - 8);
}

setInterval(updateStatus, 100);
updateStatus();
</script>
</body>
</html>
"""

# ============================================================================
# HTTP Request Handler
# ============================================================================
class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP request logs

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == "/status":
            with state_lock:
                data = {
                    "pose": shared_state["pose"],
                    "velocity": shared_state["velocity"],
                    "policy_action": shared_state["policy_action"],
                    "target": shared_state["target"],
                    "status": shared_state["status"],
                    "fps": shared_state["fps"],
                    "depth_valid_ratio": shared_state["depth_valid_ratio"],
                    "battery": shared_state["battery"],
                    "armed": shared_state["armed"],
                    "fc_mode": shared_state["fc_mode"],
                    "frame_count": shared_state["frame_count"],
                }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        elif self.path == "/depth.mjpg":
            import cv2
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    with state_lock:
                        colored = shared_state["depth_colored"]
                    if colored is not None:
                        # Downscale for faster encoding/streaming
                        small = cv2.resize(colored, (640, 360), interpolation=cv2.INTER_AREA)
                        _, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 55])
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg.tobytes())
                        self.wfile.write(b"\r\n")
                    time.sleep(0.033)  # ~30fps
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self.end_headers()


# ============================================================================
# Main: camera + policy + FC loop (same as main.py but without Foxglove)
# ============================================================================
def run_hardware_loop():
    """Read camera, run policy, read FC, update shared state."""
    import cv2

    # --- Camera ---
    try:
        import pyrealsense2 as rs
        pipeline = None
        for w, h, fps in [(1280, 720, 30), (1280, 720, 15), (640, 480, 30), (480, 270, 60)]:
            try:
                config = rs.config()
                config.enable_stream(rs.stream.depth, w, h, rs.format.z16, fps)
                pipeline = rs.pipeline()
                pipeline.start(config)
                frames = pipeline.wait_for_frames(3000)
                if frames and frames.get_depth_frame():
                    print(f"[Camera] D430 started: {w}x{h}@{fps}")
                    break
                pipeline.stop()
                pipeline = None
            except Exception:
                try: pipeline.stop()
                except: pass
                time.sleep(0.5)
        if pipeline is None:
            raise RuntimeError("Camera failed")
    except Exception as e:
        print(f"[Camera] FAILED: {e}, using simulated depth")
        pipeline = None

    # --- Policy ---
    try:
        sys.path.insert(0, str(Path(__file__).parent / "repo"))
        from deployment.rk3588.inference import RK3588Policy
        model_path = str(Path(__file__).parent / "repo" / "deployment" / "onnx" / "policy.onnx")
        policy = RK3588Policy(model_path, use_npu=False)
        print("[Policy] Loaded")
    except Exception as e:
        print(f"[Policy] FAILED: {e}")
        policy = None

    # --- Flight Controller ---
    try:
        from pymavlink import mavutil
        fc = mavutil.mavlink_connection("/dev/ttyACM0", baud=921600)
        fc.wait_heartbeat(timeout=5)
        print("[FC] Connected")
    except Exception as e:
        print(f"[FC] FAILED: {e}, using simulated state")
        fc = None

    # --- Main loop ---
    frame_count = 0
    fps_time = time.time()
    fps_count = 0
    sim_depth_frame = 0
    sim_pos = np.array([0.0, 0.0, 0.1])

    print("[LOOP] Starting main loop...")
    while True:
        try:
            t0 = time.time()

            # Get depth
            depth = None
            if pipeline:
                try:
                    frames = pipeline.wait_for_frames(1000)
                    depth_frame = frames.get_depth_frame()
                    if depth_frame:
                        depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                except Exception:
                    pass
            if depth is None:
                # Simulated depth
                sim_depth_frame += 1
                h, w = 480, 640
                yy, xx = np.mgrid[0:h, 0:w]
                depth = 3.0 + 0.01 * xx + 0.005 * np.sin(sim_depth_frame * 0.1)
                depth = depth.astype(np.float32)
                depth += np.random.randn(h, w).astype(np.float32) * 0.1

            # Colorize depth
            depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
            depth_vis = (depth_vis * 255).astype(np.uint8)
            depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

            # Read FC state
            pos = sim_pos.copy()
            vel = np.zeros(3)
            yaw = 0.0
            roll = pitch = 0.0
            armed = False
            fc_mode = "SIM"
            battery = 12.0
            if fc:
                try:
                    for _ in range(10):
                        msg = fc.recv_match(blocking=False)
                        if msg is None:
                            break
                        mt = msg.get_type()
                        if mt == "ATTITUDE":
                            roll, pitch, yaw = msg.roll, msg.pitch, msg.yaw
                        elif mt == "LOCAL_POSITION_NED":
                            pos = np.array([msg.x, msg.y, -msg.z])
                            vel = np.array([msg.vx, msg.vy, -msg.vz])
                        elif mt == "HEARTBEAT":
                            armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                            fc_mode = f"MODE_{msg.custom_mode}"
                        elif mt == "SYS_STATUS":
                            battery = msg.voltage_battery / 1000.0
                except Exception:
                    pass

            # Run policy
            action = {"ax": 0.0, "ay": 0.0, "az": 0.0}
            if policy and depth is not None:
                try:
                    result = policy.infer(depth, pos, vel, yaw, TARGET_POS)
                    action = {
                        "ax": float(result["accel"][0]),
                        "ay": float(result["accel"][1]),
                        "az": float(result["accel"][2]),
                    }
                except Exception as e:
                    pass

            # Valid depth ratio
            valid_ratio = float(np.count_nonzero(depth > 0) / depth.size)

            # FPS
            fps_count += 1
            if time.time() - fps_time > 1.0:
                fps = fps_count
                fps_count = 0
                fps_time = time.time()
            else:
                fps = shared_state["fps"]

            # Update shared state
            with state_lock:
                shared_state["depth_colored"] = depth_colored
                shared_state["pose"] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2]),
                                        "roll": float(roll), "pitch": float(pitch), "yaw": float(yaw)}
                shared_state["velocity"] = {"x": float(vel[0]), "y": float(vel[1]), "z": float(vel[2])}
                shared_state["policy_action"] = action
                shared_state["target"] = {"x": float(TARGET_POS[0]), "y": float(TARGET_POS[1]), "z": float(TARGET_POS[2])}
                shared_state["status"] = (f"FRAME={frame_count} | armed={armed} mode={fc_mode} | "
                                          f"pos=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) | "
                                          f"policy=({action['ax']:.2f},{action['ay']:.2f},{action['az']:.2f}) | "
                                          f"depth_valid={valid_ratio*100:.0f}%")
                shared_state["fps"] = fps
                shared_state["depth_valid_ratio"] = valid_ratio
                shared_state["battery"] = battery
                shared_state["armed"] = armed
                shared_state["fc_mode"] = fc_mode
                shared_state["frame_count"] = frame_count
                shared_state["trajectory"].append(pos.copy())
                if len(shared_state["trajectory"]) > 500:
                    shared_state["trajectory"].pop(0)

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"[LOOP] frame={frame_count} fps={fps} depth_valid={valid_ratio*100:.0f}% "
                      f"pos=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) policy=({action['ax']:.2f},{action['ay']:.2f},{action['az']:.2f})")

            # Maintain ~30fps
            elapsed = time.time() - t0
            if elapsed < 0.033:
                time.sleep(0.033 - elapsed)

        except Exception as e:
            print(f"[LOOP] Error: {e}")
            traceback.print_exc()
            time.sleep(0.5)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-hardware", action="store_true", help="Simulate everything")
    args = parser.parse_args()

    # Start hardware loop in background thread
    if not args.no_hardware:
        hw_thread = threading.Thread(target=run_hardware_loop, daemon=True)
        hw_thread.start()
    else:
        print("[SIM] No hardware mode - using simulated data")
        # Start a simple simulation thread
        def sim_loop():
            import cv2
            frame = 0
            while True:
                frame += 1
                h, w = 480, 640
                yy, xx = np.mgrid[0:h, 0:w]
                depth = 3.0 + 0.02 * xx + 0.01 * np.sin(frame * 0.05)
                depth += np.random.randn(h, w).astype(np.float32) * 0.1
                depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
                depth_vis = (depth_vis * 255).astype(np.uint8)
                colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
                t = frame * 0.02
                pos = np.array([2 * np.sin(t), 1.5 * np.cos(t), 1.0 + 0.2 * np.sin(t * 2)])
                with state_lock:
                    shared_state["depth_colored"] = colored
                    shared_state["pose"] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2]),
                                            "roll": 0.1*np.sin(t), "pitch": 0.1*np.cos(t), "yaw": t}
                    shared_state["velocity"] = {"x": 0.5*np.cos(t), "y": -0.5*np.sin(t), "z": 0.1*np.cos(t*2)}
                    shared_state["policy_action"] = {"ax": 3*np.cos(t), "ay": 2*np.sin(t), "az": 8.5+0.5*np.sin(t)}
                    shared_state["status"] = f"SIM frame={frame}"
                    shared_state["fps"] = 30
                    shared_state["depth_valid_ratio"] = 0.85
                    shared_state["battery"] = 12.4
                    shared_state["armed"] = True
                    shared_state["fc_mode"] = "GUIDED"
                    shared_state["frame_count"] = frame
                time.sleep(0.033)
        threading.Thread(target=sim_loop, daemon=True).start()

    # Start HTTP server (threading to allow MJPEG + JSON concurrently)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), RequestHandler)
    server.daemon_threads = True
    print(f"[HTTP] Dashboard running on http://0.0.0.0:{args.port}")
    print(f"[HTTP] Open in browser: http://<pi-ip>:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HTTP] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
