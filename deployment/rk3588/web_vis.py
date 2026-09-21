#!/usr/bin/env python3
"""
E2E-RL Drone - Web Visualization + Manual Takeoff + Auto Avoidance + Tag Landing
Flow:
1. User manually takes off with RC transmitter (POSCTL mode)
2. Dashboard shows "READY FOR AUTO" when drone is armed and flying
3. User clicks "开始自动避障" button -> OFFBOARD avoidance policy
4. User clicks "Tag 降落" button -> ArUco tag detection + autonomous landing
Run on Orange Pi 5: python3 web_vis.py [--port 8080]
Open in browser: http://192.168.1.215:8080
"""
import sys
import os
import time
import json
import threading
import traceback
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import numpy as np

# ============================================================================
# Training-consistent observation/action module (shared with offline benchmark)
# ============================================================================
try:
    from deployment.common import upstream_obs as uo
except ImportError:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
        from upstream_obs import uo
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import upstream_obs as uo

# ============================================================================
# Configuration
# ============================================================================
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# Target point B for upstream avoidance policy
AVOIDANCE_TARGET = np.array([5.0, 0.0, 1.5])
MAX_SPEED = float(os.environ.get("E2E_MAX_SPEED", "1.5"))  # m/s; test flights: export E2E_MAX_SPEED=0.5
ACCEL_LIMIT = 2.0  # m/s^2 net accel clip for avoidance
DEPTH_ROTATE = 0   # 0 = no rotation; 180 = rotate depth/IR 180 deg if dashboard image is upside-down
DEPTH_RANGE = (0.3, 24.0)

# --- Tag Landing Configuration ---
TAG_MARKER_SIZE = 0.15       # meters, physical size of ArUco marker (15cm black square)
TAG_DICT_NAME = "DICT_4X4_50"  # ArUco dictionary
TAG_LOST_TIMEOUT = 2.0        # seconds before safe hover on tag loss
TAG_ALIGN_ERROR_XY = 0.15     # meters, horizontal alignment threshold
TAG_ALIGN_STABLE_TIME = 0.5   # seconds of stable alignment before descend
TAG_DESCEND_SPEED = 0.3       # m/s, downward speed during landing
TAG_MAX_HORIZONTAL_SPEED = 0.5  # m/s, max horizontal velocity during align
TAG_KP_XY = 0.8               # P-gain for horizontal alignment (1/s)
TAG_KD_XY = 0.3               # D-gain for horizontal alignment
TAG_LAND_HEIGHT = 0.2         # meters AGL, trigger landed
TAG_SEARCH_YAW_RATE = 0.15    # rad/s, slow yaw rotation during search
TAG_IR_STREAM = True          # enable infrared stream (ArUco detection, D430 has no RGB)

# Auto control states
AUTO_IDLE = "IDLE"
AUTO_READY = "READY"
AUTO_ACTIVE = "ACTIVE"
AUTO_STOPPING = "STOPPING"

# Tag landing states
TAG_IDLE = "TAG_IDLE"
TAG_SEARCH = "TAG_SEARCH"      # searching for tag (hover or slow rotate)
TAG_ALIGN = "TAG_ALIGN"        # horizontal alignment over tag
TAG_DESCEND = "TAG_DESCEND"    # descending while maintaining alignment
TAG_LANDED = "TAG_LANDED"      # landing complete
TAG_LOST = "TAG_LOST"          # tag lost, safe hover

# Shared state
state_lock = threading.Lock()
shared_state = {
    "depth_frame": None,
    "depth_colored": None,
    "color_frame": None,
    "tag_overlay": None,
    "pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
    "velocity": {"x": 0, "y": 0, "z": 0},
    "policy_action": {"ax": 0, "ay": 0, "az": 0},
    "policy_vpred": {"vx": 0, "vy": 0, "vz": 0},
    "target": {"x": float(AVOIDANCE_TARGET[0]), "y": float(AVOIDANCE_TARGET[1]), "z": float(AVOIDANCE_TARGET[2])},
    "status": "INIT",
    "fps": 0,
    "depth_valid_ratio": 0,
    "battery": 0,
    "armed": False,
    "fc_mode": "UNKNOWN",
    "auto_state": AUTO_IDLE,
    "auto_enabled": False,
    "policy_name": "upstream_avoidance",
    "policy_desc": "DiffPhys论文原版避障策略 checkpoint0004",
    "frame_count": 0,
    "velocity_setpoint": {"vx": 0, "vy": 0, "vz": 0},
    # Tag landing state
    "tag_state": TAG_IDLE,
    "tag_detected": False,
    "tag_id": -1,
    "tag_position": {"x": 0, "y": 0, "z": 0},  # body NED: fwd, right, down
    "tag_distance": 0.0,
    "tag_horizontal_error": 0.0,
    "key_reject": "",
    "auto_reject": "",
    "tag_reject": "",
}

# Control commands (set by HTTP handler, read by control thread)
control_lock = threading.Lock()
control_cmd = {
    "start": False,
    "stop": False,
    "tag_land_start": False,
    "tag_land_stop": False,
    "key_start": False,
    "key_stop": False,
    "key_vx": 0.0,
    "key_vy": 0.0,
    "key_vz": 0.0,
    "key_land": False,
}
key_active = False
key_landing = False

# ============================================================================
# HTML Dashboard
# ============================================================================
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>E2E-RL 无人机避障+降落实控制台</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', sans-serif; padding: 10px; }
  .header { text-align: center; padding: 12px; background: #161b22; border-radius: 8px; margin-bottom: 10px; border: 1px solid #30363d; }
  .header h1 { color: #58a6ff; font-size: 22px; }
  .header .status { color: #7ee787; font-size: 14px; margin-top: 4px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
  .panel { background: #161b22; border-radius: 8px; padding: 12px; border: 1px solid #30363d; }
  .panel h2 { color: #58a6ff; font-size: 14px; margin-bottom: 8px; border-bottom: 1px solid #30363d; padding-bottom: 4px; }
  .depth-container { text-align: center; }
  .depth-container img { width: 100%; max-height: 320px; border-radius: 4px; background: #000; }
  .telemetry { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 13px; }
  .telemetry .item { background: #0d1117; padding: 6px 8px; border-radius: 4px; border: 1px solid #21262d; }
  .telemetry .label { color: #8b949e; font-size: 11px; }
  .telemetry .value { color: #fff; font-size: 16px; font-weight: bold; }
  .bar-container { margin: 4px 0; }
  .bar-label { font-size: 11px; color: #8b949e; display: flex; justify-content: space-between; }
  .bar-bg { background: #0d1117; height: 16px; border-radius: 3px; overflow: hidden; border: 1px solid #21262d; }
  .bar-fill { height: 100%; transition: width 0.1s; border-radius: 3px; }
  .bar-vx { background: #f78166; }
  .bar-vy { background: #d29922; }
  .bar-vz { background: #7ee787; }
  .trajectory-canvas { width: 100%; height: 200px; background: #0d1117; border-radius: 4px; border: 1px solid #21262d; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; margin-right: 6px; }
  .badge-ok { background: #1a7f37; color: #fff; }
  .badge-warn { background: #9e6a03; color: #fff; }
  .badge-err { background: #da3633; color: #fff; }
  .badge-info { background: #1f6feb; color: #fff; }
  .control-panel { text-align: center; padding: 16px; }
  .btn { padding: 12px 28px; font-size: 16px; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; margin: 6px; transition: all 0.2s; }
  .btn-start { background: #1a7f37; color: #fff; }
  .btn-start:hover:not(:disabled) { background: #2ea043; transform: scale(1.05); }
  .btn-stop { background: #da3633; color: #fff; }
  .btn-stop:hover:not(:disabled) { background: #f85149; transform: scale(1.05); }
  .btn-land { background: #9e6a03; color: #fff; }
  .btn-land:hover:not(:disabled) { background: #bb8009; transform: scale(1.05); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .auto-status { font-size: 18px; font-weight: bold; margin: 10px 0; padding: 8px; border-radius: 6px; }
  .auto-idle { color: #8b949e; background: #21262d; }
  .auto-ready { color: #d29922; background: #2d2400; }
  .auto-active { color: #7ee787; background: #0d2818; animation: pulse 1.5s infinite; }
  .auto-stopping { color: #f78166; background: #2d1600; }
  .key-ind { padding: 4px 10px; border: 1px solid #30363d; border-radius: 6px; font-size: 12px; color: #8b949e; background: #161b22; transition: all .1s; user-select: none; }
  .key-ind.on { border-color: #58a6ff; color: #fff; background: #1f6feb; box-shadow: 0 0 8px rgba(88,166,255,.5); }
  .tag-status { font-size: 18px; font-weight: bold; margin: 10px 0; padding: 8px; border-radius: 6px; }
  .tag-idle { color: #8b949e; background: #21262d; }
  .tag-search { color: #58a6ff; background: #0d2137; animation: pulse 1.5s infinite; }
  .tag-align { color: #d29922; background: #2d2400; }
  .tag-descend { color: #f0883e; background: #2d1600; animation: pulse 1s infinite; }
  .tag-landed { color: #7ee787; background: #0d2818; }
  .tag-lost { color: #f85149; background: #2d1015; animation: pulse 0.8s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
  .target-input { display: flex; gap: 8px; align-items: center; justify-content: center; margin-top: 10px; }
  .target-input label { font-size: 12px; color: #8b949e; }
  .target-input input { width: 60px; padding: 4px; background: #0d1117; color: #fff; border: 1px solid #30363d; border-radius: 4px; text-align: center; }
  .status-text { font-size: 12px; color: #8b949e; line-height: 1.8; font-family: monospace; }
  .tag-info { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 13px; margin-top: 8px; }
  .tag-info .item { background: #0d1117; padding: 6px 8px; border-radius: 4px; border: 1px solid #21262d; }
  .tag-info .label { color: #8b949e; font-size: 11px; }
  .tag-info .value { color: #7ee787; font-size: 16px; font-weight: bold; }
</style>
</head>
<body>
<div class="header">
  <h1>E2E-RL 无人机避障 + Tag 降落控制台</h1>
  <div class="status" id="conn-status">连接中...</div>
  <div class="status" style="color:#f0883e;">JS心跳: <span id="js-tick">0</span></div>
</div>
<div class="grid">
  <div class="panel">
    <h2>深度相机 (RealSense D430) <span id="depth-source" style="font-size:12px;color:#f85149;"></span></h2>
    <div class="depth-container">
      <img src="/depth.mjpg" alt="深度图" onerror="this.style.opacity=0.3">
    </div>
    <div style="margin-top:8px; font-size:11px; color:#8b949e;">
      暖色=近 | 冷色=远 | Policy输入: 12x16 maxpool
    </div>
  </div>
  <div class="panel">
    <h2>彩色流 + Tag 检测 <span id="tag-badge" style="font-size:12px;color:#8b949e;">未检测</span></h2>
    <div class="depth-container">
      <img src="/tag.mjpg" alt="Tag检测" onerror="this.style.opacity=0.3">
    </div>
    <div class="tag-info">
      <div class="item"><div class="label">Tag ID</div><div class="value" id="tag-id">--</div></div>
      <div class="item"><div class="label">距离</div><div class="value" id="tag-dist">--</div></div>
      <div class="item"><div class="label">前偏移</div><div class="value" id="tag-fwd">--</div></div>
      <div class="item"><div class="label">右偏移</div><div class="value" id="tag-right">--</div></div>
    </div>
  </div>
  <div class="panel">
    <h2>遥测数据</h2>
    <div class="telemetry">
      <div class="item"><div class="label">位置 X（前）</div><div class="value" id="pos-x">0.00</div></div>
      <div class="item"><div class="label">位置 Y（右）</div><div class="value" id="pos-y">0.00</div></div>
      <div class="item"><div class="label">高度 Z</div><div class="value" id="pos-z">0.00</div></div>
      <div class="item"><div class="label">航向角 Yaw</div><div class="value" id="yaw">0.0°</div></div>
      <div class="item"><div class="label">飞行速度</div><div class="value" id="vel">0.00 m/s</div></div>
      <div class="item"><div class="label">相机帧率</div><div class="value" id="fps">0</div></div>
      <div class="item"><div class="label">电池电压</div><div class="value" id="batt">0.0V</div></div>
      <div class="item"><div class="label">深度有效像素</div><div class="value" id="depth-valid">0%</div></div>
    </div>
    <div style="margin-top:10px;">
      <span class="badge" id="armed-badge">未解锁</span>
      <span class="badge" id="mode-badge">未知</span>
    </div>
  </div>
  <div class="panel control-panel">
    <h2>自动避障控制</h2>
    <div class="auto-status auto-idle" id="auto-status">等待起飞...</div>
    <button class="btn btn-start" id="btn-start" disabled onclick="startAuto()">▶ 开始自动避障</button>
    <button class="btn btn-stop" id="btn-stop" disabled onclick="stopAuto()">■ 停止自动控制</button>
    <div style="margin-top:12px; font-size:11px; color:#8b949e; text-align:left;">
      <b>操作流程：</b><br>
      1. 遥控器手动起飞到安全高度<br>
      2. 保持 POSCTL 模式，飞机稳定悬停<br>
      3. 点击"开始自动避障"<br>
      4. Policy 自动飞行并避障<br>
      5. 点击"停止"或遥控器切回手动
    </div>
  </div>
  <div class="panel control-panel">
    <h2>Tag 自动降落</h2>
    <div class="tag-status tag-idle" id="tag-status">未激活</div>
    <button class="btn btn-land" id="btn-tag-start" disabled onclick="startTagLand()">🎯 开始 Tag 降落</button>
    <button class="btn btn-stop" id="btn-tag-stop" disabled onclick="stopTagLand()">■ 停止降落</button>
    <div style="margin-top:12px; font-size:11px; color:#8b949e; text-align:left;">
      <b>降落流程：</b><br>
      1. 手动起飞到安全高度（≥1.5m）<br>
      2. 将 tag 放在飞机下方/后方地面<br>
      3. 点击"开始 Tag 降落"<br>
      4. 自动搜索 → 对齐 → 下降 → 着陆<br>
      5. 紧急情况切遥控器手动
    </div>
  </div>
  <div class="panel">
    <h2>净加速度指令（发给飞控）</h2>
    <div class="bar-container">
      <div class="bar-label"><span>前向加速 AX</span><span id="sp-vx">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vx" id="sp-vx-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>右向加速 AY</span><span id="sp-vy">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vy" id="sp-vy-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>升向加速 AZ</span><span id="sp-vz">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vz" id="sp-vz-bar" style="width:50%"></div></div>
    </div>
  </div>
  <div class="panel">
    <h2>Policy 加速度输出（原始）</h2>
    <div class="bar-container">
      <div class="bar-label"><span>前向 AX</span><span id="ax-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vx" id="ax-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>右向 AY</span><span id="ay-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vy" id="ay-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>升向 AZ</span><span id="az-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vz" id="az-bar" style="width:50%"></div></div>
    </div>
  </div>
  <div class="panel control-panel">
    <h2>键盘遥控</h2>
    <div id="key-status" class="auto-status auto-idle" style="margin-bottom:10px;">未激活</div>
    <button id="btn-key-start" onclick="keyStart()" style="background:#3b82f6;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;margin:4px;">开始键盘控制</button>
    <button id="btn-key-stop" onclick="keyStop()" style="background:#8b1a1a;color:#fff;border:none;padding:8px 16px;border-radius:6px;cursor:pointer;margin:4px;">停止</button>
    <div style="margin-top:8px;font-size:12px;color:#8b949e;text-align:left;">
      <b>W</b>前 <b>S</b>后 <b>A</b>左 <b>D</b>右<br>
      <b>空格</b>上升 <b>Q</b>下降 <b>Z</b>一键降落<br>
      速度 0.5 m/s，松开自动停
    </div>
    <div id="key-cmd-line" style="margin-top:8px;font-size:15px;font-weight:bold;color:#58a6ff;min-height:22px;">未激活</div>
    <div style="display:flex;gap:5px;margin-top:6px;flex-wrap:wrap;justify-content:center;">
      <div id="k-w" class="key-ind">W 前</div>
      <div id="k-s" class="key-ind">S 后</div>
      <div id="k-a" class="key-ind">A 左</div>
      <div id="k-d" class="key-ind">D 右</div>
      <div id="k-space" class="key-ind">空格↑</div>
      <div id="k-q" class="key-ind">Q↓</div>
      <div id="k-z" class="key-ind">Z 降落</div>
    </div>
    <div style="margin-top:6px;font-size:12px;color:#3fb950;">定高：光流｜不按空格/Q 自动保持当前高度</div>
  </div>
  <div class="panel">
    <h2>飞行指令</h2>
    <div style="display:flex; align-items:center; gap:16px;">
      <canvas id="vel-arrow" width="120" height="120" style="flex-shrink:0"></canvas>
      <div style="flex:1; font-size:13px;">
        <div>指令前进速度: <b id="v-fwd" style="color:#58a6ff; font-size:18px;">0.00</b> m/s</div>
        <div style="margin-top:4px;">指令侧移速度: <b id="v-lat" style="color:#d29922; font-size:18px;">0.00</b> m/s</div>
        <div style="margin-top:4px;">指令总速: <b id="v-total" style="color:#3fb950; font-size:18px;">0.00</b> m/s</div>
        <div style="margin-top:6px; font-size:11px; color:#8b949e;">绿箭头=实际速度<br>橙箭头=指令方向</div>
      </div>
    </div>
  </div>
  <div class="panel">
    <h2>飞行轨迹（俯视图）</h2>
    <canvas class="trajectory-canvas" id="traj-canvas"></canvas>
    <div style="margin-top:6px; font-size:11px; color:#8b949e;">
      <span style="color:#f78166;">●</span> 无人机 |
      <span style="color:#7ee787;">●</span> 目标点 |
      <span style="color:#d29922;">━</span> 轨迹
    </div>
  </div>
  <div class="panel">
    <h2>实际指令</h2>
    <div id="cmd-desc" style="font-size:16px; line-height:1.8; min-height:90px; padding:8px; background:#161b22; border-radius:6px;">等待数据...</div>
  </div>
</div>
<div class="panel" style="margin-top:10px;">
  <h2>运行状态</h2>
  <div style="font-size:11px; color:#58a6ff; margin-bottom:6px;" id="policy-info">模型加载中...</div>
  <div class="status-text" id="status-text">等待数据...</div>
</div>
<script>
let trajPoints = [];
const MAX_TRAJ = 500;
async function updateStatus() {
  try {
    const resp = await fetch('/status');
    const s = await resp.json();
    document.getElementById('conn-status').textContent = '已连接 | ' + new Date().toLocaleTimeString();
    document.getElementById('conn-status').style.color = '#7ee787';
    document.getElementById('pos-x').textContent = s.pose.x.toFixed(2);
    document.getElementById('pos-y').textContent = s.pose.y.toFixed(2);
    document.getElementById('pos-z').textContent = s.pose.z.toFixed(2);
    document.getElementById('yaw').textContent = (s.pose.yaw * 180 / Math.PI).toFixed(1) + '°';
    const vel = Math.sqrt(s.velocity.x**2 + s.velocity.y**2 + s.velocity.z**2);
    document.getElementById('vel').textContent = vel.toFixed(2) + ' m/s';
    document.getElementById('fps').textContent = s.fps;
    document.getElementById('batt').textContent = s.battery.toFixed(1) + 'V';
    document.getElementById('depth-valid').textContent = (s.depth_valid_ratio * 100).toFixed(0) + '%';
    const ds = document.getElementById('depth-source');
    if (s.depth_source === 'SIMULATED') {
        ds.textContent = '⚠ 模拟深度';
        ds.style.color = '#f85149';
    } else {
        ds.textContent = '✓ 真实深度';
        ds.style.color = '#3fb950';
    }
    // Tag display
    const tb = document.getElementById('tag-badge');
    if (s.tag_detected) {
        tb.textContent = '✓ 检测到 Tag #' + s.tag_id;
        tb.style.color = '#3fb950';
        document.getElementById('tag-id').textContent = s.tag_id;
        document.getElementById('tag-dist').textContent = s.tag_distance.toFixed(2) + 'm';
        document.getElementById('tag-fwd').textContent = s.tag_position.x.toFixed(2) + 'm';
        document.getElementById('tag-right').textContent = s.tag_position.y.toFixed(2) + 'm';
    } else {
        tb.textContent = '未检测';
        tb.style.color = '#8b949e';
        document.getElementById('tag-id').textContent = '--';
        document.getElementById('tag-dist').textContent = '--';
        document.getElementById('tag-fwd').textContent = '--';
        document.getElementById('tag-right').textContent = '--';
    }
    const armedBadge = document.getElementById('armed-badge');
    armedBadge.textContent = s.armed ? '已解锁' : '未解锁';
    armedBadge.className = 'badge ' + (s.armed ? 'badge-warn' : 'badge-ok');
    document.getElementById('mode-badge').textContent = s.fc_mode;
    // Net acceleration bars (sent to FC)
    const sp = s.velocity_setpoint || {vx:0,vy:0,vz:0};
    document.getElementById('sp-vx').textContent = sp.vx.toFixed(2);
    document.getElementById('sp-vy').textContent = sp.vy.toFixed(2);
    document.getElementById('sp-vz').textContent = sp.vz.toFixed(2);
    document.getElementById('sp-vx-bar').style.width = (50 + sp.vx * 16.7) + '%';
    document.getElementById('sp-vy-bar').style.width = (50 + sp.vy * 16.7) + '%';
    document.getElementById('sp-vz-bar').style.width = (50 + sp.vz * 16.7) + '%';
    // Raw policy accel bars
    const ax = Math.max(-5, Math.min(5, s.policy_action.ax));
    const ay = Math.max(-5, Math.min(5, s.policy_action.ay));
    const az = Math.max(-5, Math.min(5, s.policy_action.az));
    document.getElementById('ax-val').textContent = ax.toFixed(2);
    document.getElementById('ay-val').textContent = ay.toFixed(2);
    document.getElementById('az-val').textContent = az.toFixed(2);
    document.getElementById('ax-bar').style.width = (50 + ax * 10) + '%';
    document.getElementById('ay-bar').style.width = (50 + ay * 10) + '%';
    document.getElementById('az-bar').style.width = (50 + az * 10) + '%';
    document.getElementById('v-fwd').textContent = s.policy_vpred.vx.toFixed(2);
    document.getElementById('v-lat').textContent = s.policy_vpred.vy.toFixed(2);
    const vTotal = Math.sqrt(s.policy_vpred.vx**2 + s.policy_vpred.vy**2);
    document.getElementById('v-total').textContent = vTotal.toFixed(2);
    // Keyboard control status
    const keyStatus = document.getElementById('key-status');
    if (keyStatus) {
      key_active = s.key_active;
      key_landing = s.key_landing;
      key_reject = s.key_reject || '';
      auto_reject = s.auto_reject || '';
      tag_reject = s.tag_reject || '';
      if (key_landing) {
        keyStatus.textContent = '● 降落中 (LAND)';
        keyStatus.className = 'auto-status auto-stopping';
      } else {
        keyStatus.textContent = key_active ? '● 键盘控制中' : '未激活';
        keyStatus.className = 'auto-status ' + (key_active ? 'auto-active' : 'auto-idle');
      }
    }
    // Auto state
    const autoStatus = document.getElementById('auto-status');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    autoStatus.textContent = {
      'IDLE': '等待起飞...',
      'READY': '✓ 已就绪',
      'ACTIVE': '● 自动避障中...',
      'STOPPING': '正在停止...'
    }[s.auto_state] || s.auto_state;
    if (s.auto_state !== 'ACTIVE' && auto_reject) {
      autoStatus.textContent = '⚠ ' + auto_reject;
      autoStatus.className = 'auto-status auto-idle';
    } else {
      autoStatus.className = 'auto-status auto-' + s.auto_state.toLowerCase();
    }
    btnStart.disabled = !(s.auto_state === 'READY' && s.tag_state === 'TAG_IDLE');
    btnStop.disabled = !(s.auto_state === 'ACTIVE');
    // Tag state
    const tagStatus = document.getElementById('tag-status');
    const btnTagStart = document.getElementById('btn-tag-start');
    const btnTagStop = document.getElementById('btn-tag-stop');
    const tagTexts = {
      'TAG_IDLE': '未激活',
      'TAG_SEARCH': '🔍 搜索 Tag 中...',
      'TAG_ALIGN': '🎯 水平对齐中...',
      'TAG_DESCEND': '⬇ 下降中...',
      'TAG_LANDED': '✅ 着陆完成',
      'TAG_LOST': '⚠ Tag 丢失，悬停中'
    };
    tagStatus.textContent = tagTexts[s.tag_state] || s.tag_state;
    if (s.tag_state === 'TAG_IDLE' && tag_reject) {
      tagStatus.textContent = '⚠ ' + tag_reject;
    }
    tagStatus.className = 'tag-status tag-' + s.tag_state.replace('TAG_', '').toLowerCase();
    btnTagStart.disabled = !(s.auto_state === 'READY' && s.tag_state === 'TAG_IDLE');
    btnTagStop.disabled = !(s.tag_state !== 'TAG_IDLE' && s.tag_state !== 'TAG_LANDED');
    // Command description
    let cmdText = "<b>模式: " + s.auto_state + "</b>";
    if (s.key_active) {
        const kc = s.key_cmd || {vx:0,vy:0,vz:0};
        let d = [];
        if (Math.abs(kc.vx) > 0.01) d.push((kc.vx > 0 ? '前' : '后') + ' ' + Math.abs(kc.vx).toFixed(2));
        if (Math.abs(kc.vy) > 0.01) d.push((kc.vy > 0 ? '右' : '左') + ' ' + Math.abs(kc.vy).toFixed(2));
        if (Math.abs(kc.vz) > 0.01) d.push((kc.vz < 0 ? '上升' : '下降') + ' ' + Math.abs(kc.vz).toFixed(2));
        cmdText += " | <b style='color:#58a6ff'>键盘遥控</b><br>指令: " + (d.length ? d.join(' + ') + " m/s" : "悬停（光流定高）");
    } else if (s.tag_state !== 'TAG_IDLE') {
        cmdText += " | <b style='color:#f0883e'>降落: " + s.tag_state + "</b>";
        cmdText += "<br>净指令: (" + sp.vx.toFixed(2) + ", " + sp.vy.toFixed(2) + ", " + sp.vz.toFixed(2) + ") m/s²";
    } else {
        cmdText += "<br>净指令: (" + sp.vx.toFixed(2) + ", " + sp.vy.toFixed(2) + ", " + sp.vz.toFixed(2) + ") m/s²";
    }
    document.getElementById('cmd-desc').innerHTML = cmdText;
    // Policy info
    if (s.policy_name) {
      document.getElementById('policy-info').textContent = s.policy_name + ' | ' + s.policy_desc;
    }
    document.getElementById('status-text').textContent = s.status;
    // Trajectory
    trajPoints.push([s.pose.x, s.pose.y]);
    if (trajPoints.length > MAX_TRAJ) trajPoints.shift();
    drawTrajectory(s.target);
  } catch(e) {
    document.getElementById('conn-status').textContent = '连接断开: ' + e.message;
    document.getElementById('conn-status').style.color = '#f85149';
  }
}
function drawArrow(ctx, x1, y1, x2, y2, color) {
  const dx = x2-x1, dy = y2-y1;
  const len = Math.sqrt(dx*dx+dy*dy);
  if(len < 3) return;
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  const ang = Math.atan2(dy, dx);
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - 8*Math.cos(ang-0.4), y2 - 8*Math.sin(ang-0.4));
  ctx.lineTo(x2 - 8*Math.cos(ang+0.4), y2 - 8*Math.sin(ang+0.4));
  ctx.closePath(); ctx.fill();
}
function drawTrajectory(target) {
  const canvas = document.getElementById('traj-canvas');
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth;
  const h = canvas.height = canvas.offsetHeight;
  ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, w, h);
  if (trajPoints.length < 2) return;
  let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity;
  trajPoints.forEach(p => { minX=Math.min(minX,p[0]); maxX=Math.max(maxX,p[0]); minY=Math.min(minY,p[1]); maxY=Math.max(maxY,p[1]); });
  minX=Math.min(minX,target.x); maxX=Math.max(maxX,target.x);
  minY=Math.min(minY,target.y); maxY=Math.max(maxY,target.y);
  const range=Math.max(maxX-minX, maxY-minY, 1);
  const pad=20, scale=Math.min(w-2*pad,h-2*pad)/range;
  const cx=(minX+maxX)/2, cy=(minY+maxY)/2;
  const toPx=(x,y)=>[pad+(x-cx+range/2)*scale, h-pad-(y-cy+range/2)*scale];
  ctx.strokeStyle='#21262d'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){ctx.beginPath();ctx.moveTo(pad+i*(w-2*pad)/4,pad);ctx.lineTo(pad+i*(w-2*pad)/4,h-pad);ctx.stroke();ctx.beginPath();ctx.moveTo(pad,pad+i*(h-2*pad)/4);ctx.lineTo(w-pad,pad+i*(h-2*pad)/4);ctx.stroke();}
  ctx.strokeStyle='#d29922'; ctx.lineWidth=2; ctx.beginPath();
  trajPoints.forEach((p,i)=>{const[px,py]=toPx(p[0],p[1]);if(i===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);});
  ctx.stroke();
  const[tx,ty]=toPx(target.x,target.y);
  ctx.fillStyle='#7ee787';ctx.beginPath();ctx.arc(tx,ty,8,0,Math.PI*2);ctx.fill();
  const last=trajPoints[trajPoints.length-1];
  const[dx,dy]=toPx(last[0],last[1]);
  ctx.fillStyle='#f78166';ctx.beginPath();ctx.arc(dx,dy,6,0,Math.PI*2);ctx.fill();
}
async function startAuto() {
  let data = {};
  try {
    const resp = await fetch('/start_auto', {method:'POST'});
    data = await resp.json().catch(() => ({}));
  } catch(e) { return; }
  if (!data.ok && data.msg) {
    const el = document.getElementById('auto-status');
    if (el) el.textContent = '⚠ ' + data.msg;
  }
}
async function stopAuto() {
  const resp = await fetch('/stop_auto', {method:'POST'});
  const data = await resp.json();
  console.log('stop_auto:', data);
}
async function startTagLand() {
  let data = {};
  try {
    const resp = await fetch('/tag_land_start', {method:'POST'});
    data = await resp.json().catch(() => ({}));
  } catch(e) { return; }
  if (!data.ok && data.msg) {
    tag_reject = data.msg;
    const el = document.getElementById('tag-status');
    if (el) el.textContent = '⚠ ' + data.msg;
  }
}
async function stopTagLand() {
  const resp = await fetch('/tag_land_stop', {method:'POST'});
  const data = await resp.json();
  console.log('tag_land_stop:', data);
}
let key_active = false;
let key_reject = '';
let auto_reject = '';
let tag_reject = '';
let key_landing = false;
const KEY_SPEED = 0.5; // m/s
let keys = {};
async function keyStart() {
  let data = {};
  try {
    const resp = await fetch('/key_start', {method:'POST'});
    data = await resp.json().catch(() => ({}));
  } catch(e) {
    const line = document.getElementById('key-cmd-line');
    if (line) line.textContent = '⚠ 连接失败，无法启动';
    return;
  }
  if (data.ok) {
    key_active = true;
    key_landing = false;
    updateKeyStatus();
    updateKeyIndicator();
  } else {
    key_active = false;
    keys = {};
    const line = document.getElementById('key-cmd-line');
    if (line) line.textContent = '⚠ ' + (data.msg || '无法启动键盘控制');
    updateKeyStatus();
    updateKeyIndicator();
  }
}
async function keyStop() {
  await fetch('/key_stop', {method:'POST'});
  key_active = false;
  keys = {};
  sendKeyUpdate();
  updateKeyStatus();
  updateKeyIndicator();
}
function updateKeyStatus() {
  const el = document.getElementById('key-status');
  if (el) {
    el.textContent = key_active ? '● 键盘控制中' : '未激活';
    el.className = 'auto-status ' + (key_active ? 'auto-active' : 'auto-idle');
  }
}
async function sendKeyUpdate() {
  if (!key_active) return;
  let vx = 0, vy = 0, vz = 0;
  if (keys['w']) vx += KEY_SPEED;
  if (keys['s']) vx -= KEY_SPEED;
  if (keys['d']) vy += KEY_SPEED;
  if (keys['a']) vy -= KEY_SPEED;
  if (keys[' ']) vz -= KEY_SPEED * 0.7; // up
  if (keys['q']) vz += KEY_SPEED * 0.7; // down
  await fetch('/key_update', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({vx, vy, vz})});
}
function updateKeyIndicator() {
  const line = document.getElementById('key-cmd-line');
  if (!line) return;
  const set = (id, on) => { const el = document.getElementById(id); if (el) el.className = 'key-ind' + (on ? ' on' : ''); };
  set('k-w', !!keys['w']); set('k-s', !!keys['s']); set('k-a', !!keys['a']); set('k-d', !!keys['d']);
  set('k-space', !!keys[' ']); set('k-q', !!keys['q']);
  if (key_landing) { line.textContent = '✈ 一键降落中（LAND 模式）'; return; }
  if (!key_active) {
    line.textContent = key_reject ? ('⚠ ' + key_reject) : '未激活';
    return;
  }
  let parts = [];
  if (keys['w']) parts.push('前 0.5');
  if (keys['s']) parts.push('后 0.5');
  if (keys['a']) parts.push('左 0.5');
  if (keys['d']) parts.push('右 0.5');
  if (keys[' ']) parts.push('升 0.35');
  if (keys['q']) parts.push('降 0.35');
  line.textContent = parts.length ? '指令：' + parts.join(' + ') + ' m/s' : '悬停（光流定高）';
}
document.addEventListener('keydown', function(e) {
  const k = e.key.toLowerCase();
  if (k === 'z') {
    if (key_active && !key_landing) {
      fetch('/key_land', {method:'POST'});
      key_landing = true;
      key_active = false;
      keys = {};
      updateKeyIndicator();
      updateKeyStatus();
    }
    e.preventDefault();
    return;
  }
  if (['w','a','s','d',' ','q'].includes(k)) {
    if (!keys[k]) {
      keys[k] = true;
      sendKeyUpdate();
      updateKeyIndicator();
    }
    e.preventDefault();
  }
});
document.addEventListener('keyup', function(e) {
  const k = e.key.toLowerCase();
  if (['w','a','s','d',' ','q'].includes(k)) {
    if (keys[k]) {
      keys[k] = false;
      sendKeyUpdate();
      updateKeyIndicator();
    }
    e.preventDefault();
  }
});
let _tickCount = 0;
setInterval(function() { _tickCount++; const el=document.getElementById('js-tick'); if(el) el.textContent=_tickCount; }, 200);
setInterval(updateStatus, 100);
updateStatus();
</script>
</body>
</html>
"""

# ============================================================================
# ArUco Tag Detector
# ============================================================================
class TagDetector:
    """Detect ArUco markers from RealSense color stream and estimate pose."""

    ARUCO_DICTS = {
        "DICT_4X4_50": 0,
        "DICT_4X4_100": 1,
        "DICT_4X4_250": 2,
        "DICT_4X4_1000": 3,
        "DICT_5X5_50": 4,
        "DICT_5X5_100": 5,
        "DICT_5X5_250": 6,
        "DICT_5X5_100": 7,
        "DICT_6X6_50": 8,
        "DICT_6X6_100": 9,
        "DICT_6X6_250": 10,
        "DICT_6X6_1000": 11,
    }

    def __init__(self, marker_size=0.10, dict_name="DICT_4X4_50"):
        import cv2
        self.cv2 = cv2
        self.marker_size = marker_size
        self.aruco_dict = None
        self.aruco_params = None
        self.camera_matrix = None
        self.dist_coeffs = None
        self._init_aruco(dict_name)

    def _init_aruco(self, dict_name):
        """Initialize ArUco dictionary and detector parameters."""
        cv2 = self.cv2
        dict_id = self.ARUCO_DICTS.get(dict_name, 0)
        # Support both old and new OpenCV ArUco API
        try:
            # OpenCV 4.7+
            self.aruco_dict = cv2.aruco.Dictionary_get(dict_id)
            self.aruco_params = cv2.aruco.DetectorParameters_create()
            print(f"[TagDetector] ArUco initialized (legacy API): {dict_name}")
        except Exception:
            try:
                # OpenCV 4.7+ new API
                self.aruco_dict = cv2.aruco.getPredefinedDictionary(dict_id)
                self.aruco_params = cv2.aruco.DetectorParameters()
                self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
                print(f"[TagDetector] ArUco initialized (new API): {dict_name}")
            except Exception as e:
                print(f"[TagDetector] FAILED to initialize ArUco: {e}")
                raise

    def set_camera_intrinsics(self, intrinsics):
        """Set camera intrinsics from RealSense profile.
        intrinsics: pyrealsense2.intrinsics object
        """
        self.camera_matrix = np.array([
            [intrinsics.fx, 0, intrinsics.ppx],
            [0, intrinsics.fy, intrinsics.ppy],
            [0, 0, 1]
        ], dtype=np.float64)
        self.dist_coeffs = np.array(intrinsics.coeffs, dtype=np.float64)
        print(f"[TagDetector] Camera intrinsics set: fx={intrinsics.fx:.1f} fy={intrinsics.fy:.1f} "
              f"pp=({intrinsics.ppx:.1f},{intrinsics.ppy:.1f})")

    def detect(self, color_image):
        """Detect ArUco markers in color image.
        Returns: list of dicts with keys: id, corners, center, tvec, rvec
        """
        cv2 = self.cv2
        gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)

        try:
            # Try new API first
            if hasattr(self, 'detector'):
                corners, ids, rejected = self.detector.detectMarkers(gray)
            else:
                corners, ids, rejected = cv2.aruco.detectMarkers(
                    gray, self.aruco_dict, parameters=self.aruco_params)
        except Exception as e:
            return []

        results = []
        if ids is not None and len(ids) > 0:
            for i in range(len(ids)):
                tag_id = int(ids[i]) if getattr(ids, "ndim", 2) == 1 else int(ids[i][0])
                corner = corners[i]
                center = corner[0].mean(axis=0)

                # Estimate pose via cv2.solvePnP (OpenCV 5.0 removed estimatePoseSingleMarkers)
                tvec = None
                rvec = None
                if self.camera_matrix is not None and self.dist_coeffs is not None:
                    try:
                        half = self.marker_size / 2.0
                        objp = np.array([
                            [-half,  half, 0],
                            [ half,  half, 0],
                            [ half, -half, 0],
                            [-half, -half, 0],
                        ], dtype=np.float32)
                        imgp = corner[0].astype(np.float32)
                        flag = cv2.SOLVEPNP_IPPE_SQUARE if hasattr(cv2, 'SOLVEPNP_IPPE_SQUARE') else cv2.SOLVEPNP_ITERATIVE
                        retval, rvec, tvec = cv2.solvePnP(objp, imgp, self.camera_matrix, self.dist_coeffs, flags=flag)
                        rvec = rvec.flatten()
                        tvec = tvec.flatten()
                    except Exception:
                        pass

                results.append({
                    "id": tag_id,
                    "corners": corner,
                    "center": center,
                    "tvec": tvec,
                    "rvec": rvec,
                })

        return results

    def draw_detections(self, image, detections):
        """Draw detected markers and axes on image for visualization."""
        cv2 = self.cv2
        vis = image.copy()
        for det in detections:
            corners = det["corners"]
            cv2.aruco.drawDetectedMarkers(vis, [corners], np.array([[det["id"]]]))
            if det["rvec"] is not None and det["tvec"] is not None and self.camera_matrix is not None:
                cv2.drawFrameAxes(vis, self.camera_matrix, self.dist_coeffs,
                                  det["rvec"], det["tvec"], self.marker_size * 0.5)
        return vis

    def tvec_to_body_ned(self, tvec):
        """Convert tvec (camera frame) to body NED frame.

        Camera frame: x_right, y_down, z_forward (optical axis)
        Camera is mounted backward (180° flipped around optical axis):
          camera_forward -> body_backward
          camera_right -> body_left (when looking backward)
          camera_down -> body_down

        Body NED: x_forward, y_right, z_down
        """
        # tvec: [cam_x_right, cam_y_down, cam_z_forward]
        body_fwd = -tvec[2]   # camera forward = body backward
        body_right = -tvec[0]  # camera right = body left
        body_down = tvec[1]    # camera down = body down
        return np.array([body_fwd, body_right, body_down])


# ============================================================================
# Upstream Avoidance Policy (ONNX) - TRAINING-CONSISTENT CHAIN
# ============================================================================
class UpstreamAvoidancePolicy:
    """Upstream DiffPhys avoidance policy.

    Uses deployment/common/upstream_obs.py as the SINGLE observation/action
    implementation — identical to the offline benchmark:
      D430 raw depth (m) -> upstream_obs.preprocess_depth()  [conservative
        area-min FOV remap + inverse depth + 4x4 maxpool, invalid-depth stats]
      -> upstream_obs.build_state()  [yaw-only frame R, TRUE body-up from
        PX4 roll/pitch/yaw, fixed margin 0.2 (training [0.1,0.3] distribution)]
      -> upstream_avoidance.onnx
      -> upstream_obs.decode_action()  [net_accel_world = R @ (a_pred - v_pred)]
      -> PX4

    Removed legacy bugs: INTER_AREA resize, margin=min(depth), body_up=[0,0,1],
    accel/vpred sign flips, net_accel=accel_world (dropped v_pred).
    """
    def __init__(self, onnx_path, margin=0.2, max_speed=MAX_SPEED, intrinsics=None):
        import onnxruntime as ort
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.hidden = np.zeros((1, 192), dtype=np.float32)
        self.margin = float(margin)          # fixed, inside training [0.1,0.3]
        self.max_speed = float(max_speed)
        self.intrinsics = intrinsics or {}   # {fx, fy, cx, cy}; {} -> D430 nominal
        print(f"[Policy] Upstream avoidance loaded (training-consistent): {onnx_path}")

    def reset(self):
        self.hidden = np.zeros((1, 192), dtype=np.float32)

    def infer(self, depth, pos, vel, roll, pitch, yaw, target):
        """Run one policy step with the training-identical chain.

        depth: raw depth in METERS, shape (H, W) (480x640 z16/1000).
        pos/vel: world NEU (x=north, y=east, z=up) — PX4 NED with z negated.
        roll/pitch/yaw: PX4 ATTITUDE (rad, MAVLink convention).
        target: world NEU target point.
        """
        pp = uo.preprocess_depth(depth, mode="conservative", fov_remap=True,
                                 intrinsics=self.intrinsics)
        R = uo.yaw_only_frame(yaw)
        body_up = uo.body_up_world_neu(roll, pitch, yaw)
        target_v = uo.clamp_target_velocity(
            np.asarray(target, dtype=np.float64) - pos, self.max_speed)
        state = uo.build_state(vel, target_v, body_up, self.margin, R=R)

        outputs = self.session.run(None, {
            "depth": pp["input"],
            "state": state.reshape(1, 10),
            "gru_hidden": self.hidden,
        })
        self.hidden = outputs[2]
        dec = uo.decode_action(outputs[0][0], R)
        return {
            "raw_action": outputs[0][0],
            "accel_body": dec["accel_body"],
            "accel_world": dec["accel_world"],
            "vpred_body": dec["vpred_body"],
            "vpred_world": dec["vpred_world"],
            "net_accel_world": dec["net_accel_world"],
            "margin": self.margin,
            "target_v_body": state[3:6],
            "body_up_world": body_up,
            "fwd": R[:, 0],
            "yaw": yaw,
            "depth_stats": pp["stats"],
            "processed_min": float(pp["x64"].min()),
        }

class FlightDataRecorder:
    """Append-only CSV recorder for flight diagnostics (Level 4 replay).

    Records observation + policy action + final PX4 command + safety flags at
    loop rate, buffered and flushed every 0.5 s.  Controlled by env var
    E2E_RECORD_CSV (path); when unset, no recording.  Never raises into the
    flight loop (all wrapped).
    """
    COLS = ["t_loop", "iso", "frame", "auto", "tag", "armed", "fc_mode",
            "pos_x", "pos_y", "pos_z", "vel_x", "vel_y", "vel_z",
            "roll", "pitch", "yaw",
            "depth_valid", "depth_min", "depth_median", "depth_p5", "depth_p95",
            "near_ratio", "processed_min", "margin",
            "raw_a0", "raw_a1", "raw_a2", "raw_a3", "raw_a4", "raw_a5",
            "accel_body_x", "accel_body_y", "accel_body_z",
            "vpred_body_x", "vpred_body_y", "vpred_body_z",
            "policy_net_x", "policy_net_y", "policy_net_z",
            "cmd_ned_x", "cmd_ned_y", "cmd_ned_z",
            "brake", "policy_lat_ms"]

    def __init__(self, csv_path):
        self.path = str(csv_path)
        self._buf = []
        self._last_flush = 0.0
        try:
            need_header = not Path(self.path).exists()
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                if need_header:
                    f.write(",".join(self.COLS) + "\n")
            print(f"[Recorder] flight CSV -> {self.path}")
        except Exception as e:
            print(f"[Recorder] init FAILED: {e} (recording disabled)")
            self.path = None

    def record(self, row: dict):
        if self.path is None:
            return
        try:
            vals = [row.get(c, "") for c in self.COLS]
            self._buf.append(",".join(str(v) for v in vals))
            now = time.time()
            if now - self._last_flush > 0.5:
                self.flush(now)
        except Exception as e:
            print(f"[Recorder] record error: {e}")
            self.path = None

    def flush(self, now=None):
        if self.path is None or not self._buf:
            self._last_flush = time.time()
            return
        try:
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                f.write("\n".join(self._buf) + "\n")
            self._buf = []
            self._last_flush = time.time() if now is None else now
        except Exception as e:
            print(f"[Recorder] flush error: {e}")
            self.path = None


# PX4 OFFBOARD Controller
# ============================================================================
def _request_px4_streams(fc):
    """Explicitly ask PX4 for the telemetry web_vis needs.

    Companion links get only a minimal default stream set (HEARTBEAT,
    SYS_STATUS, ATTITUDE at low rate) until the GCS side requests intervals;
    LOCAL_POSITION_NED in particular is NOT streamed by default. Without it
    pos/vel stay frozen at init -> the carrot target is computed from a
    stale position and the policy sees zero motion feedback (drone drifts
    sideways chasing a wrong target).
    """
    try:
        for msgid, hz in ((32, 20), (30, 20), (1, 5), (74, 10)):
            # LOCAL_POSITION_NED, ATTITUDE, SYS_STATUS, VFR_HUD
            fc.mav.command_long_send(
                fc.target_system, fc.target_component,
                mavutil_module.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                msgid, int(1e6 / hz), 0, 0, 0, 0, 0)
        print("[FC] stream intervals requested (LOCAL_POSITION_NED@20Hz, ATTITUDE@20Hz, SYS_STATUS@5Hz, VFR_HUD@10Hz)")
    except Exception as e:
        print(f"[FC] stream request failed: {e}")


def _try_offboard(fc, send_zero, timeout=3.0):
    """Switch PX4 to OFFBOARD and confirm from the FC's own heartbeat.

    Sends zero setpoints at 20 Hz for the whole window (PX4 drops OFFBOARD
    without a >=1 Hz setpoint stream).  Confirms only on a PX4 heartbeat
    (autopilot=12) showing main mode OFFBOARD with the armed bit.  Returns
    (ok, reason, last_mode); prints a precise reason on failure.
    """
    ok = saw_px4 = saw_offboard = saw_armed = False
    last_mode = "?"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            send_zero()
        except Exception:
            pass
        time.sleep(0.05)
        try:
            hb = fc.recv_match(blocking=False)
            if not _is_px4_heartbeat(hb):
                continue
            saw_px4 = True
            mm = (hb.custom_mode >> 16) & 0xFF
            last_mode = {1:"MANUAL",2:"ALTCTL",3:"POSCTL",4:"AUTO",5:"ACRO",6:"OFFBOARD",7:"STABILIZED",8:"RATTITUDE",9:"LAND"}.get(mm, f"MODE_{mm}")
            if hb.base_mode & mavutil_module.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                saw_armed = True
            if mm == 6:
                saw_offboard = True
                if hb.base_mode & mavutil_module.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                    ok = True
                    break
        except Exception:
            pass
    if ok:
        reason = "confirmed"
    elif not saw_px4:
        reason = "no PX4 heartbeat in window"
    elif not saw_offboard:
        reason = f"PX4 never OFFBOARD (last {last_mode}, armed_seen={saw_armed})"
    else:
        reason = f"OFFBOARD seen but armed bit missing (armed_seen={saw_armed})"
    print(f"[OFFBOARD] ok={ok} reason={reason} last_mode={last_mode}")
    return ok, reason, last_mode


def _is_px4_heartbeat(msg):
    """True only for the flight controller's own HEARTBEAT (MAV_AUTOPILOT_PX4=12).

    Other MAVLink nodes on the bus (optical flow, peripherals) also emit
    HEARTBEAT with custom_mode=0; without this filter they could drive the
    armed/mode flags and make the OFFBOARD confirm check fail forever.
    """
    return (msg is not None and msg.get_type() == "HEARTBEAT"
            and getattr(msg, "autopilot", 0) == 12)


class PX4Controller:
    """Send velocity/acceleration setpoints to PX4 in OFFBOARD mode."""
    PX4_MODE_OFFBOARD = 6 << 16
    PX4_MODE_POSCTL = 3 << 16
    PX4_MODE_LAND = 9 << 16  # Auto Land mode

    def __init__(self, fc):
        self.fc = fc

    def send_velocity_ned(self, vx, vy, vz):
        """Send velocity setpoint in NED frame (vx=fwd, vy=right, vz=down).
        Full 3-axis velocity control (used for tag landing).
        """
        self.fc.mav.set_position_target_local_ned_send(
            0,
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000110111000111,  # velocity only mask (vx, vy, vz)
            0, 0, 0,
            vx, vy, vz,
            0, 0, 0,
            0, 0,
        )

    def send_acceleration(self, ax, ay, az):
        """Send acceleration setpoint in NED frame (XY only, Z ignored for altitude hold)."""
        self.fc.mav.set_position_target_local_ned_send(
            0,
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000110100111111,  # accel XY only (ignore Z for altitude hold)
            0, 0, 0,
            0, 0, 0,
            ax, ay, az,
            0, 0,
        )

    def send_velocity_yawrate_ned(self, vx, vy, vz, yaw_rate):
        """Send velocity setpoint with yaw rate (for search rotation)."""
        self.fc.mav.set_position_target_local_ned_send(
            0,
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000110111000100,  # velocity XYZ + yaw_rate
            0, 0, 0,
            vx, vy, vz,
            0, 0, 0,
            0, yaw_rate,
        )

    def set_mode_offboard(self):
        self.fc.mav.command_long_send(
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_CMD_DO_SET_MODE, 0,
            mavutil_module.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            self.PX4_MODE_OFFBOARD, 0, 0, 0, 0, 0
        )

    def set_mode_posctl(self):
        self.fc.mav.command_long_send(
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_CMD_DO_SET_MODE, 0,
            mavutil_module.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            self.PX4_MODE_POSCTL, 0, 0, 0, 0, 0
        )

    def set_mode_land(self):
        self.fc.mav.command_long_send(
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_CMD_DO_SET_MODE, 0,
            mavutil_module.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            self.PX4_MODE_LAND, 0, 0, 0, 0, 0
        )


mavutil_module = None


# ============================================================================
# HTTP Request Handler
# ============================================================================
class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        elif self.path == "/status":
            with state_lock:
                data = {k: v for k, v in shared_state.items()
                        if k not in ("depth_frame", "depth_colored", "color_frame", "tag_overlay")}
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
                        small = cv2.resize(colored, (640, 360), interpolation=cv2.INTER_AREA)
                        _, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 55])
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg.tobytes())
                        self.wfile.write(b"\r\n")
                    time.sleep(0.033)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/tag.mjpg":
            import cv2
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    with state_lock:
                        overlay = shared_state["tag_overlay"]
                    if overlay is not None:
                        small = cv2.resize(overlay, (640, 360), interpolation=cv2.INTER_AREA)
                        _, jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 55])
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpg)}\r\n\r\n".encode())
                        self.wfile.write(jpg.tobytes())
                        self.wfile.write(b"\r\n")
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global AVOIDANCE_TARGET
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            data = json.loads(body) if body else {}
        except:
            data = {}

        if self.path == "/start_auto":
            with state_lock:
                armed_now = shared_state.get("armed", False)
            if not armed_now:
                self._json_response({"ok": False, "reason": "not armed", "msg": "飞机未解锁，请先遥控器解锁并起飞悬停"})
            else:
                with control_lock:
                    control_cmd["start"] = True
                self._json_response({"ok": True, "msg": "开始自动避障"})
        elif self.path == "/stop_auto":
            with control_lock:
                control_cmd["stop"] = True
            self._json_response({"ok": True})
        elif self.path == "/tag_land_start":
            with state_lock:
                armed_now = shared_state.get("armed", False)
            if not armed_now:
                self._json_response({"ok": False, "reason": "not armed", "msg": "飞机未解锁，请先遥控器解锁并起飞悬停"})
            else:
                with control_lock:
                    control_cmd["tag_land_start"] = True
                self._json_response({"ok": True, "msg": "开始 Tag 降落"})
        elif self.path == "/tag_land_stop":
            with control_lock:
                control_cmd["tag_land_stop"] = True
            self._json_response({"ok": True})
        elif self.path == "/key_start":
            with state_lock:
                armed_now = shared_state.get("armed", False)
            if not armed_now:
                self._json_response({"ok": False, "reason": "not armed", "msg": "飞机未解锁，请先遥控器解锁并起飞悬停"})
            else:
                with control_lock:
                    control_cmd["key_start"] = True
                self._json_response({"ok": True, "msg": "开始键盘控制"})
        elif self.path == "/key_stop":
            with control_lock:
                control_cmd["key_stop"] = True
            self._json_response({"ok": True})
        elif self.path == "/key_land":
            with control_lock:
                control_cmd["key_land"] = True
            self._json_response({"ok": True, "msg": "一键降落"})
        elif self.path == "/key_update":
            vx = float(data.get("vx", 0))
            vy = float(data.get("vy", 0))
            vz = float(data.get("vz", 0))
            with control_lock:
                control_cmd["key_vx"] = vx
                control_cmd["key_vy"] = vy
                control_cmd["key_vz"] = vz
            self._json_response({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


# ============================================================================
# Main hardware + control loop
# ============================================================================
def run_hardware_loop():
    global AVOIDANCE_TARGET
    global mavutil_module
    global key_active
    global key_landing
    import cv2

    # --- Camera ---
    pipeline = None
    align = None
    intrinsics = None
    try:
        import pyrealsense2 as rs
        config = rs.config()
        config.enable_stream(rs.stream.depth, CAMERA_WIDTH, CAMERA_HEIGHT, rs.format.z16, CAMERA_FPS)
        if TAG_IR_STREAM:
            # Use infrared stream 1 for ArUco detection (D430 has no RGB sensor)
            config.enable_stream(rs.stream.infrared, 1, CAMERA_WIDTH, CAMERA_HEIGHT, rs.format.y8, CAMERA_FPS)
        pipeline = rs.pipeline()
        profile = pipeline.start(config)
        # Disable IR emitter to remove dot pattern for ArUco detection
        try:
            dev = profile.get_device()
            depth_sensor = dev.first_depth_sensor()
            depth_sensor.set_option(rs.option.emitter_enabled, 0)
            print("[Camera] IR emitter disabled (no dot pattern)")
        except Exception as e:
            print(f"[Camera] Could not disable emitter: {e}")
        if TAG_IR_STREAM:
            # IR and depth are co-aligned on Stereo Module (extrinsics ~ identity)
            ir_profile = profile.get_stream(rs.stream.infrared, 1)
            intrinsics = ir_profile.as_video_stream_profile().get_intrinsics()
            print(f"[Camera] IR stream 1 intrinsics: fx={intrinsics.fx:.1f} fy={intrinsics.fy:.1f}")
        print(f"[Camera] D430 started: {CAMERA_WIDTH}x{CAMERA_HEIGHT}@{CAMERA_FPS} (ir={TAG_IR_STREAM})")
    except Exception as e:
        print(f"[Camera] FAILED: {e}")
        # Try without color stream
        try:
            config = rs.config()
            config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
            if TAG_IR_STREAM:
                config.enable_stream(rs.stream.infrared, 1, 640, 480, rs.format.y8, 30)
            pipeline = rs.pipeline()
            pipeline.start(config)
            print("[Camera] D430 depth+IR fallback: 640x480@30")
        except Exception as e2:
            print(f"[Camera] Fallback also FAILED: {e2}")

    # --- Tag Detector ---
    tag_detector = None
    if TAG_IR_STREAM:
        try:
            tag_detector = TagDetector(marker_size=TAG_MARKER_SIZE, dict_name=TAG_DICT_NAME)
            if intrinsics is not None:
                tag_detector.set_camera_intrinsics(intrinsics)
            print("[TagDetector] Initialized (IR mode)")
        except Exception as e:
            print(f"[TagDetector] FAILED: {e}")
            traceback.print_exc()

    # --- Policy ---
    policy = None
    onnx_paths = [
        str(Path(__file__).parent / "upstream_avoidance.onnx"),
        str(Path(__file__).parent / "repo" / "deployment" / "onnx" / "upstream_avoidance.onnx"),
        "/home/orangepi/kswlt_e2d/upstream_avoidance.onnx",
    ]
    for p in onnx_paths:
        if Path(p).exists():
            try:
                policy = UpstreamAvoidancePolicy(p, margin=0.2, max_speed=1.5)
                break
            except Exception as e:
                print(f"[Policy] Failed to load {p}: {e}")
    if policy is None:
        print("[Policy] WARNING: no upstream_avoidance.onnx found")
    elif intrinsics is not None:
        policy.intrinsics = {"fx": float(intrinsics.fx), "fy": float(intrinsics.fy),
                             "cx": float(intrinsics.ppx), "cy": float(intrinsics.ppy)}
        print(f"[Policy] D430 intrinsics fx={intrinsics.fx:.1f} fy={intrinsics.fy:.1f} "
              f"cx={intrinsics.ppx:.1f} cy={intrinsics.ppy:.1f} (FOV remap)")

    # --- Flight Controller ---
    fc = None
    px4 = None
    try:
        from pymavlink import mavutil
        mavutil_module = mavutil
        fc = mavutil.mavlink_connection("/dev/ttyACM0", baud=921600)
        fc.wait_heartbeat(timeout=5)
        px4 = PX4Controller(fc)
        _request_px4_streams(fc)
        print("[FC] PX4 connected")
    except Exception as e:
        print(f"[FC] FAILED: {e}")

    # --- Persistent state ---
    fc_pos = np.array([0.0, 0.0, 0.1])
    fc_pos_filtered = np.array([0.0, 0.0, 0.1])
    fc_vel = np.zeros(3)
    fc_yaw = 0.0
    fc_roll = 0.0
    fc_pitch = 0.0
    fc_armed = False
    fc_mode_str = "未连接"
    fc_battery = 0.0
    fc_msg_count = 0
    fc_last_msg_time = time.time()
    auto_state = AUTO_IDLE
    auto_active = False
    frame_count = 0
    fps_time = time.time()
    fps_count = 0
    sim_depth_frame = 0

    # --- Tag landing state ---
    tag_state = TAG_IDLE
    tag_last_detected_time = 0.0
    tag_align_stable_start = 0.0
    tag_last_pos_body = np.zeros(3)
    tag_vel_prev = np.zeros(2)
    tag_dt = 0.033
    tag_land_start_pos = None
    last_depth = None
    last_color = None
    depth_colored = None
    disp_frame = 0

    # --- Flight data recorder (Level 4 replay) ---
    recorder = None
    _rec_csv = os.environ.get("E2E_RECORD_CSV", "").strip()
    if _rec_csv:
        recorder = FlightDataRecorder(_rec_csv)

    _ob_lost_t0 = time.time()

    print("[LOOP] Starting main loop...")

    while True:
        try:
            t0 = time.time()

            # --- Get frames ---
            depth = None
            color_image = None
            depth_source = "real"

            if pipeline:
                try:
                    if key_active:
                        # Fast path: do not block on camera frames; poll non-blocking, use cached frame
                        try:
                            pf = pipeline.poll_for_frames()
                            if pf:
                                depth_frame = pf.get_depth_frame()
                                ir_frame = pf.get_infrared_frame(1) if TAG_IR_STREAM else None
                                if depth_frame:
                                    last_depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                                    if DEPTH_ROTATE == 180:
                                        last_depth = cv2.rotate(last_depth, cv2.ROTATE_180)
                                if ir_frame:
                                    last_ir_gray = np.asanyarray(ir_frame.get_data())
                                    if DEPTH_ROTATE == 180:
                                        last_ir_gray = cv2.rotate(last_ir_gray, cv2.ROTATE_180)
                                    last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)
                        except Exception:
                            pass
                        depth = last_depth
                        color_image = last_color
                    else:
                        frames = pipeline.wait_for_frames(1000)
                        depth_frame = frames.get_depth_frame()
                        ir_frame = frames.get_infrared_frame(1) if TAG_IR_STREAM else None
                        if depth_frame:
                            last_depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                            if DEPTH_ROTATE == 180:
                                last_depth = cv2.rotate(last_depth, cv2.ROTATE_180)
                            depth = last_depth
                        if ir_frame:
                            last_ir_gray = np.asanyarray(ir_frame.get_data())
                            if DEPTH_ROTATE == 180:
                                last_ir_gray = cv2.rotate(last_ir_gray, cv2.ROTATE_180)
                            last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)
                            color_image = last_color
                except Exception:
                    pass

            if depth is None:
                depth_source = "SIMULATED"
                sim_depth_frame += 1
                h, w = 480, 640
                yy, xx = np.mgrid[0:h, 0:w]
                depth = 3.0 + 0.01 * xx + 0.005 * np.sin(sim_depth_frame * 0.1)
                depth = depth.astype(np.float32)
                depth += np.random.randn(h, w).astype(np.float32) * 0.1

            # Colorize depth (throttled to every 3rd frame while keyboard control active)
            disp_frame += 1
            if (not key_active) or (disp_frame % 3 == 1) or depth_colored is None:
                depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
                depth_vis = (depth_vis * 255).astype(np.uint8)
                depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

            # --- Tag detection ---
            tag_detections = []
            tag_overlay = color_image.copy() if color_image is not None else np.zeros((480, 640, 3), dtype=np.uint8)
            if tag_detector is not None and color_image is not None and not key_active:
                try:
                    # Apply CLAHE for IR overexposure compensation
                    ir_gray_eq = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)
                    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
                    ir_gray_eq = clahe.apply(ir_gray_eq)
                    kernel = np.ones((3,3), np.uint8)
                    ir_gray_eq = cv2.morphologyEx(ir_gray_eq, cv2.MORPH_OPEN, kernel)
                    ir_gray_eq = cv2.GaussianBlur(ir_gray_eq, (3, 3), 0)
                    ir_gray_eq = cv2.copyMakeBorder(ir_gray_eq, 50, 50, 50, 50, cv2.BORDER_CONSTANT, value=255)
                    color_image = cv2.cvtColor(ir_gray_eq, cv2.COLOR_GRAY2BGR)
                    tag_detections = tag_detector.detect(color_image)
                    if not tag_detections and not hasattr(tag_detector, "_dbg"):
                        tag_detector._dbg = 0
                    if not tag_detections and tag_detector._dbg < 3:
                        tag_detector._dbg += 1
                        cv2.imwrite("/tmp/ir_debug.png", ir_gray_eq)
                        print("[TAG DEBUG] saved frame", tag_detector._dbg, ir_gray_eq.shape, "mean=", int(ir_gray_eq.mean()))
                    if tag_detections:
                        tag_last_detected_time = time.time()
                        tag_overlay = tag_detector.draw_detections(color_image, tag_detections)
                except Exception as e:
                    print(f"[TAG] Detection error: {e}")

            # Get primary tag (largest / closest)
            primary_tag = None
            tag_pos_body = np.zeros(3)
            tag_distance = 0.0
            TAG_HOLD_SEC = 0.5
            now = time.time()
            if tag_detections:
                best = min(tag_detections, key=lambda d: np.linalg.norm(d["tvec"]) if d["tvec"] is not None else 999)
                primary_tag = best
                _last_tag = best
                _last_tag_time = now
                if best["tvec"] is not None:
                    tag_pos_body = tag_detector.tvec_to_body_ned(best["tvec"])
                    tag_distance = float(np.linalg.norm(best["tvec"]))
            elif now - globals().get('_last_tag_time', 0) < TAG_HOLD_SEC:
                primary_tag = globals().get('_last_tag', None)
                if primary_tag is not None and primary_tag.get("tvec") is not None:
                    tag_pos_body = tag_detector.tvec_to_body_ned(primary_tag["tvec"])
                    tag_distance = float(np.linalg.norm(primary_tag["tvec"]))

            # --- Read FC state ---
            pos = fc_pos.copy()
            vel = fc_vel.copy()
            yaw = fc_yaw
            roll = fc_roll
            pitch = fc_pitch
            armed = fc_armed
            fc_mode = fc_mode_str
            battery = fc_battery

            if fc:
                try:
                    for _ in range(20):
                        msg = fc.recv_match(blocking=False)
                        if msg is None:
                            break
                        fc_msg_count += 1
                        fc_last_msg_time = time.time()
                        mt = msg.get_type()
                        if mt == "ATTITUDE":
                            fc_roll, fc_pitch, fc_yaw = msg.roll, msg.pitch, msg.yaw
                            roll, pitch, yaw = fc_roll, fc_pitch, fc_yaw
                        elif mt == "LOCAL_POSITION_NED":
                            new_pos = np.array([msg.x, msg.y, -msg.z])
                            new_vel = np.array([msg.vx, msg.vy, -msg.vz])
                            # accept the first fix unconditionally, then gate jumps
                            if (np.linalg.norm(new_pos - fc_pos) < 2.0
                                    or np.allclose(fc_pos, np.array([0.0, 0.0, 0.1]))):
                                fc_pos = new_pos
                                fc_vel = new_vel
                                fc_pos_filtered = 0.85 * fc_pos_filtered + 0.15 * fc_pos
                            pos = fc_pos_filtered.copy()
                            vel = fc_vel.copy()
                        elif mt == "HEARTBEAT":
                            if not _is_px4_heartbeat(msg):
                                continue  # ignore other MAVLink nodes
                            fc_armed = bool(msg.base_mode & mavutil_module.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                            armed = fc_armed
                            cm = msg.custom_mode
                            main_mode = (cm >> 16) & 0xFF
                            px4_modes = {1:"MANUAL",2:"ALTCTL",3:"POSCTL",4:"AUTO",5:"ACRO",6:"OFFBOARD",7:"STABILIZED",8:"RATTITUDE",9:"LAND"}
                            fc_mode_str = px4_modes.get(main_mode, f"MODE_{main_mode}")
                            fc_mode = fc_mode_str
                        elif mt == "SYS_STATUS":
                            fc_battery = msg.voltage_battery / 1000.0
                            battery = fc_battery
                except Exception:
                    pass

            if time.time() - fc_last_msg_time > 2.0:
                fc_mode = "失联" if fc else "无飞控"

            # --- OFFBOARD watchdog: any active mode must actually stay in
            # OFFBOARD; on loss degrade gracefully (never keep sending commands
            # into a non-OFFBOARD controller) ---
            _any_active = auto_active or key_active or tag_state in (TAG_SEARCH, TAG_ALIGN, TAG_DESCEND)
            if _any_active and fc_mode != "OFFBOARD":
                if time.time() - _ob_lost_t0 > 0.5:
                    print(f"[WATCHDOG] OFFBOARD lost (mode={fc_mode}) -> auto/key/tag disabled")
                    if auto_active:
                        auto_active = False
                        auto_state = AUTO_IDLE
                        with state_lock:
                            shared_state["auto_reject"] = f"OFFBOARD 丢失（{fc_mode}），自动已停止"
                    if key_active:
                        key_active = False
                        with state_lock:
                            shared_state["key_reject"] = f"OFFBOARD 丢失（{fc_mode}），键盘已停止"
                    if tag_state in (TAG_SEARCH, TAG_ALIGN, TAG_DESCEND):
                        tag_state = TAG_IDLE
                        tag_land_start_pos = None
                        with state_lock:
                            shared_state["tag_reject"] = f"OFFBOARD 丢失（{fc_mode}），降落已停止"
            else:
                _ob_lost_t0 = time.time()

            # --- Control command processing ---
            with control_lock:
                cmd_start = control_cmd["start"]
                cmd_stop = control_cmd["stop"]
                cmd_tag_start = control_cmd["tag_land_start"]
                cmd_tag_stop = control_cmd["tag_land_stop"]
                cmd_key_start = control_cmd["key_start"]
                cmd_key_stop = control_cmd["key_stop"]
                cmd_key_vx = control_cmd["key_vx"]
                cmd_key_vy = control_cmd["key_vy"]
                cmd_key_vz = control_cmd["key_vz"]
                cmd_key_land = control_cmd["key_land"]
                control_cmd["start"] = False
                control_cmd["stop"] = False
                control_cmd["tag_land_start"] = False
                control_cmd["tag_land_stop"] = False
                control_cmd["key_start"] = False
                control_cmd["key_stop"] = False
                control_cmd["key_land"] = False

            # --- Stop avoidance ---
            if cmd_stop and auto_active:
                print("[AUTO] Stop requested -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                auto_active = False
                auto_state = AUTO_IDLE
                if policy:
                    policy.reset()
                with state_lock:
                    shared_state["auto_reject"] = ""


            # --- Start avoidance ---
            if cmd_start and not auto_active and tag_state == TAG_IDLE and not key_active:
                if armed:
                    print(f"[AUTO] Start -> OFFBOARD avoidance")
                    if px4 and fc:
                        for _ in range(20):
                            px4.send_acceleration(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok, _ob_reason, _ob_mode = _try_offboard(fc, lambda: px4.send_acceleration(0, 0, 0))
                        auto_active = offboard_ok
                        auto_state = AUTO_ACTIVE if offboard_ok else AUTO_IDLE
                        if policy:
                            policy.reset()
                        if offboard_ok:
                            with state_lock:
                                shared_state["auto_reject"] = ""
                        else:
                            print("[AUTO] OFFBOARD switch failed -> POSCTL, auto NOT active")
                            if px4:
                                try:
                                    px4.set_mode_posctl()
                                except Exception:
                                    pass
                            with state_lock:
                                shared_state["auto_reject"] = "OFFBOARD 切换失败：请确认已解锁起飞悬停后再点开始"
                        print(f"[AUTO] OFFBOARD confirmed={offboard_ok}")
                else:
                    print(f"[AUTO] Start rejected: not armed")

            # --- Tag landing start ---
            if cmd_tag_start and tag_state == TAG_IDLE and not auto_active and not key_active:
                if armed:
                    print("[TAG] Tag landing start -> OFFBOARD")
                    if px4 and fc:
                        # Send zero velocity setpoints before switching
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok, _ob_reason, _ob_mode = _try_offboard(fc, lambda: px4.send_velocity_ned(0, 0, 0))
                        if offboard_ok:
                            tag_state = TAG_SEARCH
                            tag_land_start_pos = pos.copy()
                            tag_last_detected_time = time.time()
                            with state_lock:
                                shared_state["tag_reject"] = ""
                            print("[TAG] OFFBOARD confirmed, entering SEARCH")
                        else:
                            print("[TAG] OFFBOARD switch failed -> POSCTL, tag landing NOT active")
                            if px4:
                                try:
                                    px4.set_mode_posctl()
                                except Exception:
                                    pass
                            with state_lock:
                                shared_state["tag_reject"] = "OFFBOARD 切换失败：请确认已解锁起飞悬停后再点开始"

                else:
                    print("[TAG] Start rejected: not armed")

            # --- Tag landing stop ---
            if cmd_tag_stop and tag_state != TAG_IDLE and tag_state != TAG_LANDED:
                print("[TAG] Stop requested -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                tag_state = TAG_IDLE
                tag_land_start_pos = None
                with state_lock:
                    shared_state["tag_reject"] = ""


            # --- Update auto_state for display ---
            if not auto_active and tag_state == TAG_IDLE:
                if armed:
                    auto_state = AUTO_READY
                else:
                    auto_state = AUTO_IDLE

            # --- RC OFFBOARD -> auto: flipping the RC mode switch to OFFBOARD
            # (or any armed OFFBOARD entry) starts avoidance control directly,
            # no dashboard button needed. The watchdog above keeps auto active
            # only while PX4 actually stays in OFFBOARD; flipping the switch
            # back (or link loss) disables it. ---
            if (not auto_active and not key_active
                    and tag_state == TAG_IDLE
                    and fc_mode == "OFFBOARD" and armed):
                print("[AUTO] OFFBOARD detected (RC/MAVLink) -> auto avoidance ON")
                auto_active = True
                auto_state = AUTO_ACTIVE
                with state_lock:
                    shared_state["auto_reject"] = ""

            # --- Tag landing state machine ---
            tag_vel_cmd_ned = np.zeros(3)  # velocity command: [fwd, right, down]
            tag_active_control = False

            if tag_state != TAG_IDLE and tag_state != TAG_LANDED:
                tag_active_control = True
                tag_now = time.time()
                tag_lost = (tag_now - tag_last_detected_time) > TAG_LOST_TIMEOUT

                if tag_state == TAG_SEARCH:
                    # Slow yaw rotation to find tag
                    if primary_tag is not None and primary_tag["tvec"] is not None:
                        print(f"[TAG] Found tag #{primary_tag['id']}, distance={tag_distance:.2f}m -> ALIGN")
                        tag_state = TAG_ALIGN
                        tag_align_stable_start = tag_now
                    else:
                        # Hover + slow yaw rotation
                        tag_vel_cmd_ned[2] = 0.0  # maintain altitude (no vertical velocity)
                        if px4:
                            px4.send_velocity_yawrate_ned(0, 0, 0, TAG_SEARCH_YAW_RATE)

                elif tag_state == TAG_ALIGN:
                    if tag_lost:
                        print("[TAG] Tag lost during ALIGN -> TAG_LOST")
                        tag_state = TAG_LOST
                    elif primary_tag is not None and primary_tag["tvec"] is not None:
                        # PD control: move horizontally to center over tag
                        # tag_pos_body: [fwd, right, down] in body NED
                        err_x = tag_pos_body[0]  # forward error
                        err_y = tag_pos_body[1]  # right error

                        # PD controller
                        vel_x = TAG_KP_XY * err_x
                        vel_y = TAG_KP_XY * err_y

                        # Limit horizontal speed
                        h_speed = np.sqrt(vel_x**2 + vel_y**2)
                        if h_speed > TAG_MAX_HORIZONTAL_SPEED:
                            scale = TAG_MAX_HORIZONTAL_SPEED / h_speed
                            vel_x *= scale
                            vel_y *= scale

                        tag_vel_cmd_ned[0] = vel_x  # fwd
                        tag_vel_cmd_ned[1] = vel_y  # right
                        tag_vel_cmd_ned[2] = 0.0    # maintain altitude

                        # Check alignment
                        horiz_error = np.sqrt(err_x**2 + err_y**2)
                        if horiz_error < TAG_ALIGN_ERROR_XY:
                            if tag_align_stable_start == 0:
                                tag_align_stable_start = tag_now
                            elif (tag_now - tag_align_stable_start) > TAG_ALIGN_STABLE_TIME:
                                print(f"[TAG] Aligned (err={horiz_error:.2f}m) -> DESCEND")
                                tag_state = TAG_DESCEND
                        else:
                            tag_align_stable_start = tag_now

                        if px4:
                            px4.send_velocity_ned(tag_vel_cmd_ned[0], tag_vel_cmd_ned[1], tag_vel_cmd_ned[2])
                    else:
                        # Tag not detected this frame but not yet timed out - hold position
                        if px4:
                            px4.send_velocity_ned(0, 0, 0)

                elif tag_state == TAG_DESCEND:
                    if tag_lost:
                        print("[TAG] Tag lost during DESCEND -> TAG_LOST")
                        tag_state = TAG_LOST
                    elif primary_tag is not None and primary_tag["tvec"] is not None:
                        # Continue horizontal alignment + descend
                        err_x = tag_pos_body[0]
                        err_y = tag_pos_body[1]

                        vel_x = TAG_KP_XY * err_x
                        vel_y = TAG_KP_XY * err_y

                        h_speed = np.sqrt(vel_x**2 + vel_y**2)
                        if h_speed > TAG_MAX_HORIZONTAL_SPEED:
                            scale = TAG_MAX_HORIZONTAL_SPEED / h_speed
                            vel_x *= scale
                            vel_y *= scale

                        tag_vel_cmd_ned[0] = vel_x
                        tag_vel_cmd_ned[1] = vel_y
                        tag_vel_cmd_ned[2] = TAG_DESCEND_SPEED  # descend

                        # Check if landed (altitude below threshold)
                        current_alt = pos[2]  # NEU z = altitude
                        if tag_land_start_pos is not None:
                            descended = tag_land_start_pos[2] - current_alt
                        else:
                            descended = 0

                        # Also check: tag very close (distance < 0.3m)
                        if tag_distance < 0.3:
                            print(f"[TAG] Tag distance={tag_distance:.2f}m, landing -> LANDED")
                            tag_state = TAG_LANDED
                            if px4:
                                px4.set_mode_land()
                        elif current_alt < TAG_LAND_HEIGHT:
                            print(f"[TAG] Altitude={current_alt:.2f}m, landing -> LANDED")
                            tag_state = TAG_LANDED
                            if px4:
                                px4.set_mode_land()

                        if px4 and tag_state == TAG_DESCEND:
                            px4.send_velocity_ned(tag_vel_cmd_ned[0], tag_vel_cmd_ned[1], tag_vel_cmd_ned[2])
                    else:
                        # Hold position
                        if px4:
                            px4.send_velocity_ned(0, 0, 0)

                elif tag_state == TAG_LOST:
                    # Safe hover - zero velocity
                    tag_vel_cmd_ned[:] = 0
                    if px4:
                        px4.send_velocity_ned(0, 0, 0)
                    # Try to recover
                    if primary_tag is not None and primary_tag["tvec"] is not None:
                        print("[TAG] Tag recovered -> ALIGN")
                        tag_state = TAG_ALIGN
                        tag_align_stable_start = time.time()

            # --- Run avoidance policy (for display and when active) ---
            policy_lat_ms = 0.0
            result = None
            accel_body = np.zeros(3)
            vpred_body = np.zeros(3)
            accel_world_neu = np.zeros(3)
            net_accel_neu = np.zeros(3)
            accel_setpoint_ned = np.zeros(3)

            if policy and not key_active:
                try:
                    # Continuous carrot
                    fwd_x = np.cos(yaw)
                    fwd_y = np.sin(yaw)
                    carrot_dist = 5.0
                    AVOIDANCE_TARGET = np.array([
                        pos[0] + fwd_x * carrot_dist,
                        pos[1] + fwd_y * carrot_dist,
                        pos[2] + 0.5,
                    ], dtype=np.float32)

                    _t_infer = time.perf_counter()
                    result = policy.infer(depth, pos, vel, roll, pitch, yaw, AVOIDANCE_TARGET)
                    policy_lat_ms = (time.perf_counter() - _t_infer) * 1000.0
                    accel_body = result["accel_body"]
                    vpred_body = result["vpred_body"]
                    accel_world_neu = result["accel_world"]
                    vpred_world_neu = result["vpred_world"]

                    # Training-consistent net command: net = R @ (a_pred - v_pred).
                    # v_pred is part of the action, NOT pollution (see audit §2.2).
                    net_accel_neu = result["net_accel_world"].copy()

                    # Speed limiter
                    speed = float(np.linalg.norm(vel))
                    if speed > MAX_SPEED:
                        brake = min((speed - MAX_SPEED) * 3.0, 2.0)
                        vel_dir = vel / max(speed, 0.01)
                        net_accel_neu -= vel_dir * brake

                    net_accel_neu = np.clip(net_accel_neu, -ACCEL_LIMIT, ACCEL_LIMIT)
                    accel_setpoint_ned = np.array([
                        net_accel_neu[0],
                        net_accel_neu[1],
                        -net_accel_neu[2],
                    ])
                except Exception as e:
                    print(f"[POLICY] Inference error: {e}")
                    traceback.print_exc()

            # --- Keyboard control ---
            if cmd_key_start and not auto_active and tag_state == TAG_IDLE and not key_active:
                if armed:
                    print("[KEY] Start keyboard control -> OFFBOARD")
                    if px4 and fc:
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok, _ob_reason, _ob_mode = _try_offboard(fc, lambda: px4.send_velocity_ned(0, 0, 0))
                        key_active = offboard_ok
                        key_landing = False
                        if offboard_ok:
                            with state_lock:
                                shared_state["key_reject"] = ""
                        else:
                            print("[KEY] OFFBOARD switch failed -> POSCTL, keyboard NOT active")
                            if px4:
                                try:
                                    px4.set_mode_posctl()
                                except Exception:
                                    pass
                            with state_lock:
                                shared_state["key_reject"] = "OFFBOARD 切换失败：请确认已解锁起飞悬停后再点开始"
                        print(f"[KEY] OFFBOARD confirmed={offboard_ok}")
                else:
                    print("[KEY] Start rejected: not armed")
            if cmd_key_stop and key_active:
                print("[KEY] Stop -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                key_active = False
                with state_lock:
                    shared_state["key_reject"] = ""
            if cmd_key_land and key_active:
                print("[KEY] Land requested -> LAND")
                if px4:
                    px4.set_mode_land()
                key_active = False
                key_landing = True
                with state_lock:
                    shared_state["key_reject"] = ""

            # --- Send setpoints ---
            if key_active and px4 and fc:
                # Keyboard: body frame velocity -> NED
                # W=forward(+X), S=backward(-X), A=left(-Y), D=right(+Y)
                # Space=up(-Z), Q=down(+Z)
                vx_ned = cmd_key_vx * np.cos(yaw) - cmd_key_vy * np.sin(yaw)
                vy_ned = cmd_key_vx * np.sin(yaw) + cmd_key_vy * np.cos(yaw)
                vz_ned = cmd_key_vz
                px4.send_velocity_ned(vx_ned, vy_ned, vz_ned)
            elif auto_active and px4 and fc:
                try:
                    px4.send_acceleration(
                        accel_setpoint_ned[0],
                        accel_setpoint_ned[1],
                        accel_setpoint_ned[2],
                    )
                except Exception as e:
                    print(f"[AUTO] Send error: {e}")

            # --- Valid depth ratio ---
            valid_ratio = float(np.count_nonzero(depth > 0) / depth.size)

            # --- FPS ---
            fps_count += 1
            if time.time() - fps_time > 1.0:
                fps = fps_count
                fps_count = 0
                fps_time = time.time()
            else:
                fps = shared_state["fps"]

            # --- Update shared state ---
            with state_lock:
                shared_state["depth_colored"] = depth_colored
                shared_state["tag_overlay"] = tag_overlay
                shared_state["pose"] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2]),
                                        "roll": float(roll), "pitch": float(pitch), "yaw": float(yaw)}
                shared_state["velocity"] = {"x": float(vel[0]), "y": float(vel[1]), "z": float(vel[2])}
                shared_state["policy_action"] = {"ax": float(accel_body[0]), "ay": float(accel_body[1]), "az": float(accel_body[2])}
                shared_state["policy_vpred"] = {"vx": float(vpred_body[0]), "vy": float(vpred_body[1]), "vz": float(vpred_body[2])}
                shared_state["policy_net_accel"] = {"x": float(net_accel_neu[0]), "y": float(net_accel_neu[1]), "z": float(net_accel_neu[2])}
                shared_state["velocity_setpoint"] = {
                    "vx": float(net_accel_neu[0]) if auto_active else float(tag_vel_cmd_ned[0]),
                    "vy": float(net_accel_neu[1]) if auto_active else float(tag_vel_cmd_ned[1]),
                    "vz": float(net_accel_neu[2]) if auto_active else float(tag_vel_cmd_ned[2]),
                }
                shared_state["target"] = {"x": float(AVOIDANCE_TARGET[0]), "y": float(AVOIDANCE_TARGET[1]), "z": float(AVOIDANCE_TARGET[2])}
                shared_state["auto_state"] = auto_state
                shared_state["auto_enabled"] = auto_active
                shared_state["key_active"] = key_active
                shared_state["key_landing"] = key_landing
                shared_state["key_cmd"] = {"vx": float(cmd_key_vx), "vy": float(cmd_key_vy), "vz": float(cmd_key_vz)}
                # Tag state
                shared_state["tag_state"] = tag_state
                shared_state["tag_detected"] = primary_tag is not None
                shared_state["tag_id"] = primary_tag["id"] if primary_tag else -1
                shared_state["tag_position"] = {"x": float(tag_pos_body[0]), "y": float(tag_pos_body[1]), "z": float(tag_pos_body[2])}
                shared_state["tag_distance"] = tag_distance
                shared_state["tag_horizontal_error"] = float(np.linalg.norm(tag_pos_body[:2]))
                # Status text
                tag_short = {"TAG_IDLE":"-","TAG_SEARCH":"搜索","TAG_ALIGN":"对齐","TAG_DESCEND":"下降","TAG_LANDED":"着陆","TAG_LOST":"丢失"}
                shared_state["status"] = (f"帧={frame_count} | 解锁={'是' if armed else '否'} 模式={fc_mode} | "
                                          f"自动={'ON' if auto_active else 'OFF'} | Tag={tag_short.get(tag_state, tag_state)} | "
                                          f"位置=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) | "
                                          f"深度有效={valid_ratio*100:.0f}%")
                shared_state["fps"] = fps
                shared_state["depth_valid_ratio"] = valid_ratio
                shared_state["depth_source"] = depth_source
                shared_state["battery"] = battery
                shared_state["armed"] = armed
                shared_state["fc_mode"] = fc_mode
                shared_state["frame_count"] = frame_count

            # --- Flight recorder (never raises into flight loop) ---
            if recorder is not None and policy is not None and result is not None:
                try:
                    ds = result.get("depth_stats", {})
                    recorder.record({
                        "t_loop": round(time.time() - t0, 4),
                        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                        "frame": frame_count, "auto": int(auto_active),
                        "tag": tag_state, "armed": int(armed),
                        "fc_mode": fc_mode,
                        "pos_x": pos[0], "pos_y": pos[1], "pos_z": pos[2],
                        "vel_x": vel[0], "vel_y": vel[1], "vel_z": vel[2],
                        "roll": roll, "pitch": pitch, "yaw": yaw,
                        "depth_valid": valid_ratio,
                        "depth_min": ds.get("depth_min", ""),
                        "depth_median": ds.get("median", ""),
                        "depth_p5": ds.get("p5", ""), "depth_p95": ds.get("p95", ""),
                        "near_ratio": ds.get("near_ratio", ""),
                        "processed_min": float(result.get("processed_min", 0.0)),
                        "margin": float(result.get("margin", 0.0)),
                        "raw_a0": result["raw_action"][0], "raw_a1": result["raw_action"][1],
                        "raw_a2": result["raw_action"][2], "raw_a3": result["raw_action"][3],
                        "raw_a4": result["raw_action"][4], "raw_a5": result["raw_action"][5],
                        "accel_body_x": accel_body[0], "accel_body_y": accel_body[1], "accel_body_z": accel_body[2],
                        "vpred_body_x": vpred_body[0], "vpred_body_y": vpred_body[1], "vpred_body_z": vpred_body[2],
                        "policy_net_x": result["net_accel_world"][0],
                        "policy_net_y": result["net_accel_world"][1],
                        "policy_net_z": result["net_accel_world"][2],
                        "cmd_ned_x": accel_setpoint_ned[0], "cmd_ned_y": accel_setpoint_ned[1],
                        "cmd_ned_z": accel_setpoint_ned[2],
                        "brake": int(float(np.linalg.norm(vel)) > MAX_SPEED),
                        "policy_lat_ms": round(policy_lat_ms, 3),
                    })
                except Exception as e:
                    print(f"[Recorder] error: {e}")

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"[LOOP] frame={frame_count} fps={fps} auto={auto_state} tag={tag_state} "
                      f"pos=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) "
                      f"tag_det={'YES' if primary_tag else 'NO'} dist={tag_distance:.2f}")

            elapsed = time.time() - t0
            target_period = 0.02 if key_active else 0.033
            if elapsed < target_period:
                time.sleep(target_period - elapsed)
        except Exception as e:
            print(f"[LOOP] Error: {e}")
            traceback.print_exc()
            time.sleep(0.5)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-hardware", action="store_true")
    args = parser.parse_args()

    if not args.no_hardware:
        threading.Thread(target=run_hardware_loop, daemon=True).start()
    else:
        print("[SIM] No hardware mode")
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
                pos = np.array([2*np.sin(t), 1.5*np.cos(t), 1.0+0.2*np.sin(t*2)])
                with state_lock:
                    shared_state["depth_colored"] = colored
                    shared_state["tag_overlay"] = colored
                    shared_state["pose"] = {"x":float(pos[0]),"y":float(pos[1]),"z":float(pos[2]),"roll":0,"pitch":0,"yaw":t}
                    shared_state["velocity"] = {"x":0.5*np.cos(t),"y":-0.5*np.sin(t),"z":0}
                    shared_state["status"] = f"SIM frame={frame}"
                    shared_state["fps"] = 30
                    shared_state["depth_valid_ratio"] = 0.85
                    shared_state["battery"] = 12.4
                    shared_state["armed"] = True
                    shared_state["fc_mode"] = "OFFBOARD"
                    shared_state["auto_state"] = "ACTIVE"
                    shared_state["tag_state"] = "TAG_IDLE"
                    shared_state["frame_count"] = frame
                time.sleep(0.033)
        threading.Thread(target=sim_loop, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), RequestHandler)
    server.daemon_threads = True
    print(f"[HTTP] Dashboard: http://0.0.0.0:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HTTP] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
