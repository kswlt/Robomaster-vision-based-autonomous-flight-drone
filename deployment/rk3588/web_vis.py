#!/usr/bin/env python3
"""
E2E-RL Drone - Web Visualization + Manual Takeoff + Auto Avoidance Control

Flow:
1. User manually takes off with RC transmitter (POSCTL mode)
2. Dashboard shows "READY FOR AUTO" when drone is armed and flying
3. User clicks "开始自动避障" button
4. Script switches PX4 to OFFBOARD, upstream avoidance policy takes over
5. Policy outputs velocity setpoints from depth + target + state
6. User clicks "停止自动控制" or RC switch to POSCTL to regain control

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

# Target point B for upstream avoidance policy (relative to takeoff point, NED-like)
# Default: 5m forward, 0m right, 1.5m up (in "north-east-up" convention)
AVOIDANCE_TARGET = np.array([5.0, 0.0, 1.5])

MAX_SPEED = 4.0  # m/s, matches upstream env max_speed
DEPTH_RANGE = (0.3, 24.0)

# Auto control states
AUTO_IDLE = "IDLE"
AUTO_READY = "READY"          # armed & flying, waiting for button
AUTO_ACTIVE = "ACTIVE"        # OFFBOARD policy control active
AUTO_STOPPING = "STOPPING"    # transitioning back to manual

# Shared state
state_lock = threading.Lock()
shared_state = {
    "depth_frame": None,
    "depth_colored": None,
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
}

# Control commands (set by HTTP handler, read by control thread)
control_lock = threading.Lock()
control_cmd = {"start": False, "stop": False}

# ============================================================================
# HTML Dashboard
# ============================================================================
HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>E2E-RL 无人机避障控制台</title>
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
  .depth-container img { width: 100%; max-height: 380px; border-radius: 4px; background: #000; }
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
  .btn { padding: 14px 32px; font-size: 18px; font-weight: bold; border: none; border-radius: 8px; cursor: pointer; margin: 6px; transition: all 0.2s; }
  .btn-start { background: #1a7f37; color: #fff; }
  .btn-start:hover:not(:disabled) { background: #2ea043; transform: scale(1.05); }
  .btn-stop { background: #da3633; color: #fff; }
  .btn-stop:hover:not(:disabled) { background: #f85149; transform: scale(1.05); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .auto-status { font-size: 20px; font-weight: bold; margin: 10px 0; padding: 8px; border-radius: 6px; }
  .auto-idle { color: #8b949e; background: #21262d; }
  .auto-ready { color: #d29922; background: #2d2400; }
  .auto-active { color: #7ee787; background: #0d2818; animation: pulse 1.5s infinite; }
  .auto-stopping { color: #f78166; background: #2d1600; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
  .target-input { display: flex; gap: 8px; align-items: center; justify-content: center; margin-top: 10px; }
  .target-input label { font-size: 12px; color: #8b949e; }
  .target-input input { width: 60px; padding: 4px; background: #0d1117; color: #fff; border: 1px solid #30363d; border-radius: 4px; text-align: center; }
  .status-text { font-size: 12px; color: #8b949e; line-height: 1.8; font-family: monospace; }
</style>
</head>
<body>
<div class="header">
  <h1>E2E-RL 无人机端到端避障控制台</h1>
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
      暖色=近 | 冷色=远 | 量程 0.3-24m | Policy输入: 12x16 maxpool
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
      <div class="item"><div class="label">目标(机体前/右/上)</div><div class="value" id="debug-tgt">0/0/0</div></div>
      <div class="item"><div class="label">机头方向(北/东)</div><div class="value" id="debug-fwd">0/0</div></div>
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
    <div class="target-input">
      <label>目标点:</label>
      <input type="number" id="target-x" value="5.0" step="0.5"> X(前)
      <input type="number" id="target-y" value="0.0" step="0.5"> Y(右)
      <input type="number" id="target-z" value="1.5" step="0.5"> Z(高)
      <button onclick="setTarget()" style="padding:4px 10px; background:#1f6feb; color:#fff; border:none; border-radius:4px; cursor:pointer;">设置</button>
      <button onclick="setTargetForward()" style="padding:4px 10px; background:#2da44e; color:#fff; border:none; border-radius:4px; cursor:pointer; margin-left:6px;">目标设为正前方</button>
    </div>
    <div style="margin-top:12px; font-size:11px; color:#8b949e; text-align:left;">
      <b>操作流程：</b><br>
      1. 遥控器手动起飞到安全高度<br>
      2. 保持 POSCTL 模式，飞机稳定悬停<br>
      3. 点击"开始自动避障"<br>
      4. Policy 自动飞向目标点并避障<br>
      5. 点击"停止"或遥控器切回手动
    </div>
  </div>
  <div class="panel">
    <h2>Policy 净加速度指令（发给飞控）</h2>
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
    <div style="margin-top:8px; font-size:11px; color:#8b949e;">
      范围: ±1.5 m/s² | 速度上限: 1.0 m/s | OFFBOARD 加速度控制<br>
      计算: a_net = a_pred - v_pred (净加速度, PX4自动补偿重力)
    </div>
  </div>
  <div class="panel">
    <h2>Policy 加速度输出</h2>
    <div class="bar-container">
      <div class="bar-label"><span>前向加速 AX</span><span id="ax-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vx" id="ax-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>右向加速 AY</span><span id="ay-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vy" id="ay-bar" style="width:50%"></div></div>
    </div>
    <div class="bar-container">
      <div class="bar-label"><span>升向加速 AZ</span><span id="az-val">0.00</span></div>
      <div class="bar-bg"><div class="bar-fill bar-vz" id="az-bar" style="width:50%"></div></div>
    </div>
    <div style="margin-top:8px; font-size:11px; color:#8b949e;">
      机体坐标系加速度 | action第1列
    </div>
  </div>
  <div class="panel">
    <h2>飞行指令</h2>
    <div style="display:flex; align-items:center; gap:16px;">
      <canvas id="vel-arrow" width="120" height="120" style="flex-shrink:0"></canvas>
      <div style="flex:1; font-size:13px;">
        <div>指令前进速度: <b id="v-fwd" style="color:#58a6ff; font-size:18px;">0.00</b> m/s</div>
        <div style="margin-top:4px;">指令侧移速度: <b id="v-lat" style="color:#d29922; font-size:18px;">0.00</b> m/s</div>
        <div style="margin-top:4px;">指令总速: <b id="v-total" style="color:#3fb950; font-size:18px;">0.00</b> m/s</div>
        <div style="margin-top:6px; font-size:11px; color:#8b949e;">绿箭头=实际速度方向<br>橙箭头=指令方向</div>
      </div>
    </div>
  </div>
  <div class="panel">
    <h2>实际指令（发给飞控）</h2>
    <div id="cmd-desc" style="font-size:16px; line-height:1.8; min-height:90px; padding:8px; background:#161b22; border-radius:6px;">等待数据...</div>
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
        ds.textContent = '⚠ 模拟深度（相机未连接）';
        ds.style.color = '#f85149';
    } else {
        ds.textContent = '✓ 真实深度';
        ds.style.color = '#3fb950';
    }

    // Debug info
    const dt = s.debug_target_body || {x:0,y:0,z:0};
    document.getElementById('debug-tgt').textContent = dt.x.toFixed(2) + '/' + dt.y.toFixed(2) + '/' + dt.z.toFixed(2);
    const df = s.debug_fwd || {x:0,y:0};
    document.getElementById('debug-fwd').textContent = df.x.toFixed(2) + '/' + df.y.toFixed(2);

    const armedBadge = document.getElementById('armed-badge');
    armedBadge.textContent = s.armed ? '已解锁' : '未解锁';
    armedBadge.className = 'badge ' + (s.armed ? 'badge-warn' : 'badge-ok');
    document.getElementById('mode-badge').textContent = s.fc_mode;

    // Acceleration setpoint bars (net acceleration, ±5 m/s²)
    const sp = s.velocity_setpoint || {vx:0,vy:0,vz:0};
    document.getElementById('sp-vx').textContent = sp.vx.toFixed(2);
    document.getElementById('sp-vy').textContent = sp.vy.toFixed(2);
    document.getElementById('sp-vz').textContent = sp.vz.toFixed(2);
    document.getElementById('sp-vx-bar').style.width = (50 + sp.vx * 16.7) + '%';
    document.getElementById('sp-vy-bar').style.width = (50 + sp.vy * 16.7) + '%';
    document.getElementById('sp-vz-bar').style.width = (50 + sp.vz * 16.7) + '%';

    // Acceleration bars
    const ax = Math.max(-5, Math.min(5, s.policy_action.ax));
    const ay = Math.max(-5, Math.min(5, s.policy_action.ay));
    const az = Math.max(-5, Math.min(5, s.policy_action.az));
    document.getElementById('ax-val').textContent = ax.toFixed(2);
    document.getElementById('ay-val').textContent = ay.toFixed(2);
    document.getElementById('az-val').textContent = az.toFixed(2);
    document.getElementById('ax-bar').style.width = (50 + ax * 10) + '%';
    document.getElementById('ay-bar').style.width = (50 + ay * 10) + '%';
    document.getElementById('az-bar').style.width = (50 + az * 10) + '%';

    // Flight velocity visualization
    const velData = s.velocity || {x:0, y:0, z:0};
    const yaw = (s.pose && s.pose.yaw) || 0;
    const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
    // Actual velocity in body frame (for green arrow)
    const actFwd = velData.x * cosY + velData.y * sinY;
    const actRight = -velData.x * sinY + velData.y * cosY;
    // Commanded velocity from policy (vpred in body frame) - this is what policy wants
    const vp = s.policy_vpred || {vx:0, vy:0, vz:0};
    document.getElementById('v-fwd').textContent = vp.vx.toFixed(2);
    document.getElementById('v-lat').textContent = vp.vy.toFixed(2);
    const vTotal = Math.sqrt(vp.vx*vp.vx + vp.vy*vp.vy);
    document.getElementById('v-total').textContent = vTotal.toFixed(2);

    // Draw arrows on canvas
    const vc = document.getElementById('vel-arrow');
    const vctx = vc.getContext('2d');
    const vw = vc.width, vh = vc.height;
    const cx = vw/2, cy = vh/2;
    vctx.fillStyle = '#0d1117';
    vctx.fillRect(0,0,vw,vh);
    // Draw cross
    vctx.strokeStyle = '#30363d';
    vctx.lineWidth = 1;
    vctx.beginPath(); vctx.moveTo(cx,10); vctx.lineTo(cx,vh-10); vctx.stroke();
    vctx.beginPath(); vctx.moveTo(10,cy); vctx.lineTo(vw-10,cy); vctx.stroke();
    // Draw actual velocity arrow (green)
    const scale = 40; // px per m/s
    const avx = actFwd * scale, avy = -actRight * scale; // canvas: right=+x, up=-y
    drawArrow(vctx, cx, cy, cx + avx, cy + avy, '#3fb950');
    // Draw commanded acceleration arrow (orange, scaled)
    const sp2 = s.velocity_setpoint || {vx:0, vy:0};
    const sFwd = sp2.vx * cosY + sp2.vy * sinY;
    const sRight = -sp2.vx * sinY + sp2.vy * cosY;
    const sa = 20; // accel arrow scale
    const cax = sFwd * sa, cay = -sRight * sa;
    drawArrow(vctx, cx, cy, cx + cax, cy + cay, '#f78166');

    // Plain language command description (net accel = what PX4 actually receives)
    const sp3 = s.velocity_setpoint || {vx:0,vy:0,vz:0};
    const axN = sp3.vx, ayN = sp3.vy;
    let cmdText = "";
    // Horizontal direction
    const speed = Math.sqrt(axN*axN + ayN*ayN);
    if (speed < 0.05) {
      cmdText += "<b>停止/悬停</b>（无水平加速度）";
    } else {
      // Determine direction in body frame (rotate by yaw)
      const yaw2 = (s.pose && s.pose.yaw) || 0;
      const cY = Math.cos(yaw2), sY = Math.sin(yaw2);
      const bodyFwd = axN * cY + ayN * sY;
      const bodyRight = -axN * sY + ayN * cY;
      let dirs = [];
      if (bodyFwd > 0.3) dirs.push("前进");
      else if (bodyFwd < -0.3) dirs.push("后退");
      if (bodyRight > 0.3) dirs.push("右移");
      else if (bodyRight < -0.3) dirs.push("左移");
      if (dirs.length === 0) {
        if (bodyFwd > 0) dirs.push("微前进");
        else if (bodyFwd < 0) dirs.push("微后退");
        if (bodyRight > 0) dirs.push("微右移");
        else if (bodyRight < 0) dirs.push("微左移");
      }
      cmdText += "<b>" + dirs.join("、") + "</b>";
      cmdText += " " + speed.toFixed(2) + " m/s²";
    }
    // Vertical
    const azN = sp3.vz;
    if (Math.abs(azN) > 0.2) {
      cmdText += "，" + (azN > 0 ? "<b>下降</b>" : "<b>上升</b>") + " " + Math.abs(azN).toFixed(2) + " m/s²";
    } else {
      cmdText += "，<b>定高</b>";
    }
    // Auto state
    const autoTxt = s.auto_state === 'ACTIVE' ? '<span style="color:#3fb950">● 自动飞行中</span>' : '<span style="color:#8b949e">○ 手动/待命</span>';
    cmdText += "<br><span style='font-size:13px; color:#8b949e'>" + autoTxt + "</span>";
    document.getElementById('cmd-desc').innerHTML = cmdText;

    // Auto control status
    const autoStatus = document.getElementById('auto-status');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    autoStatus.textContent = {
      'IDLE': '等待起飞...',
      'READY': '✓ 已就绪 - 点击开始自动避障',
      'ACTIVE': '● 自动避障中...',
      'STOPPING': '正在停止...'
    }[s.auto_state] || s.auto_state;
    autoStatus.className = 'auto-status auto-' + s.auto_state.toLowerCase();
    btnStart.disabled = !(s.auto_state === 'READY');
    btnStop.disabled = !(s.auto_state === 'ACTIVE');

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
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  // Arrowhead
  const ang = Math.atan2(dy, dx);
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - 8*Math.cos(ang-0.4), y2 - 8*Math.sin(ang-0.4));
  ctx.lineTo(x2 - 8*Math.cos(ang+0.4), y2 - 8*Math.sin(ang+0.4));
  ctx.closePath();
  ctx.fill();
}

function drawTrajectory(target) {
  const canvas = document.getElementById('traj-canvas');
  const ctx = canvas.getContext('2d');
  const w = canvas.width = canvas.offsetWidth;
  const h = canvas.height = canvas.offsetHeight;
  ctx.fillStyle = '#0d1117';
  ctx.fillRect(0, 0, w, h);
  if (trajPoints.length < 2) return;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  trajPoints.forEach(p => { minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]); minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); });
  minX = Math.min(minX, target.x); maxX = Math.max(maxX, target.x);
  minY = Math.min(minY, target.y); maxY = Math.max(maxY, target.y);
  const range = Math.max(maxX - minX, maxY - minY, 1);
  const pad = 20;
  const scale = Math.min(w - 2*pad, h - 2*pad) / range;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const toPx = (x, y) => [pad + (x - cx + range/2) * scale, h - pad - (y - cy + range/2) * scale];

  ctx.strokeStyle = '#21262d'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    ctx.beginPath(); ctx.moveTo(pad + i*(w-2*pad)/4, pad); ctx.lineTo(pad + i*(w-2*pad)/4, h-pad); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pad, pad + i*(h-2*pad)/4); ctx.lineTo(w-pad, pad + i*(h-2*pad)/4); ctx.stroke();
  }
  ctx.strokeStyle = '#d29922'; ctx.lineWidth = 2; ctx.beginPath();
  trajPoints.forEach((p, i) => { const [px, py] = toPx(p[0], p[1]); if (i===0) ctx.moveTo(px, py); else ctx.lineTo(px, py); });
  ctx.stroke();
  const [tx, ty] = toPx(target.x, target.y);
  ctx.fillStyle = '#7ee787'; ctx.beginPath(); ctx.arc(tx, ty, 8, 0, Math.PI*2); ctx.fill();
  ctx.fillStyle = '#fff'; ctx.font = '10px sans-serif'; ctx.fillText('目标', tx+10, ty-8);
  const last = trajPoints[trajPoints.length-1];
  const [dx, dy] = toPx(last[0], last[1]);
  ctx.fillStyle = '#f78166'; ctx.beginPath(); ctx.arc(dx, dy, 6, 0, Math.PI*2); ctx.fill();
  ctx.fillStyle = '#fff'; ctx.fillText('无人机', dx+10, dy-8);
}

async function startAuto() {
  const tx = parseFloat(document.getElementById('target-x').value);
  const ty = parseFloat(document.getElementById('target-y').value);
  const tz = parseFloat(document.getElementById('target-z').value);
  const resp = await fetch('/start_auto', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({target:[tx,ty,tz]})});
  const data = await resp.json();
  console.log('start_auto:', data);
}
async function stopAuto() {
  const resp = await fetch('/stop_auto', {method:'POST'});
  const data = await resp.json();
  console.log('stop_auto:', data);
}
async function setTarget() {
  const tx = parseFloat(document.getElementById('target-x').value);
  const ty = parseFloat(document.getElementById('target-y').value);
  const tz = parseFloat(document.getElementById('target-z').value);
  const resp = await fetch('/set_target', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({target:[tx,ty,tz]})});
  const data = await resp.json();
  console.log('set_target:', data);
}
async function setTargetForward() {
  const resp = await fetch('/set_target_forward', {method:'POST'});
  const data = await resp.json();
  if (data.ok) {
    document.getElementById('target-x').value = data.target[0].toFixed(2);
    document.getElementById('target-y').value = data.target[1].toFixed(2);
    document.getElementById('target-z').value = data.target[2].toFixed(2);
  }
  console.log('set_target_forward:', data);
}

// JS alive counter
let _tickCount = 0;
setInterval(function() {
  _tickCount++;
  const el = document.getElementById('js-tick');
  if (el) el.textContent = _tickCount;
}, 200);
setInterval(updateStatus, 100);
updateStatus();
</script>
</body>
</html>
"""

# ============================================================================
# Upstream Avoidance Policy (ONNX)
# ============================================================================
class UpstreamAvoidancePolicy:
    """Load upstream DiffPhys avoidance checkpoint (ONNX) and run inference."""

    def __init__(self, onnx_path):
        import onnxruntime as ort
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.hidden = np.zeros((1, 192), dtype=np.float32)
        print(f"[Policy] Upstream avoidance loaded: {onnx_path}")

    def reset(self):
        self.hidden = np.zeros((1, 192), dtype=np.float32)

    def infer(self, depth, pos, vel, yaw, target):
        """
        depth: HxW float32 meters
        pos: (3,) north-east-up
        vel: (3,) north-east-up
        yaw: radians
        target: (3,) north-east-up target point
        Returns: dict with accel_body, vpred_body, vpred_world
        """
        import cv2

        # --- Body frame rotation matrix (columns: fwd, right, up in world) ---
        fwd = np.array([np.cos(yaw), np.sin(yaw), 0.0])
        right = np.array([-np.sin(yaw), np.cos(yaw), 0.0])
        up = np.array([0.0, 0.0, 1.0])
        R = np.stack([fwd, right, up], axis=1)  # 3x3, body->world

        # --- Depth preprocessing (exact match to upstream) ---
        d = np.clip(depth, 0.3, 24.0)
        x = 3.0 / d - 0.6  # inverse depth normalized
        # Resize to 48x64 then maxpool 4x -> 12x16
        x_small = cv2.resize(x, (64, 48), interpolation=cv2.INTER_AREA)
        # MaxPool 4x
        x_12x16 = x_small.reshape(12, 4, 16, 4).max(axis=(1, 3))
        depth_input = x_12x16.reshape(1, 1, 12, 16).astype(np.float32)

        # --- State vector (10-dim): [local_v(3), target_v(3), up_world(3), margin(1)] ---
        local_v_body = R.T @ vel  # world->body
        target_v_world = target - pos
        target_norm = np.linalg.norm(target_v_world)
        if target_norm > 1e-6:
            target_v_unit = target_v_world / target_norm
            target_v_clamped = target_v_unit * min(target_norm, MAX_SPEED)
        else:
            target_v_clamped = np.zeros(3)
        target_v_body = R.T @ target_v_clamped
        up_world = R[:, 2]  # up vector in world frame (matches env.R[:,2])
        margin = float(np.min(depth[depth > 0])) if np.any(depth > 0) else 0.2
        margin = min(max(margin, 0.1), 0.3)

        state = np.concatenate([local_v_body, target_v_body, up_world, [margin]]).astype(np.float32)
        state_input = state.reshape(1, 10)

        # --- ONNX inference ---
        outputs = self.session.run(None, {
            "depth": depth_input,
            "state": state_input,
            "gru_hidden": self.hidden,
        })
        action = outputs[0][0]  # (6,)
        self.hidden = outputs[2]  # (1, 192)

        # --- Decode action: reshape (3,2) = [accel_body, vpred_body] ---
        act_mat = action.reshape(3, 2)
        accel_body = act_mat[:, 0].copy()
        vpred_body = act_mat[:, 1].copy()

        # Camera mounted backwards (180 deg yaw): flip body x and y
        accel_body[0] *= -1.0
        accel_body[1] *= -1.0
        vpred_body[0] *= -1.0
        vpred_body[1] *= -1.0

        # Transform to world frame
        accel_world = R @ accel_body
        vpred_world = R @ vpred_body

        return {
            "accel_body": accel_body,
            "accel_world": accel_world,
            "vpred_body": vpred_body,
            "vpred_world": vpred_world,
            "margin": margin,
            "state": state,
            "target_v_body": target_v_body,
            "fwd": fwd,
            "yaw": yaw,
        }


# ============================================================================
# PX4 OFFBOARD velocity setpoint sender
# ============================================================================
class PX4Controller:
    """Send velocity setpoints to PX4 in OFFBOARD mode."""

    PX4_MODE_OFFBOARD = 6 << 16
    PX4_MODE_POSCTL = 3 << 16  # POSCTL = position control (manual)

    def __init__(self, fc):
        self.fc = fc
        self.active = False

    def send_velocity(self, vx_ned, vy_ned, vz_ned):
        """Send velocity setpoint in NED frame (vz positive = down)."""
        self.fc.mav.set_position_target_local_ned_send(
            0,
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000110111000111,  # velocity only mask
            0, 0, 0,  # position (ignored)
            vx_ned, vy_ned, vz_ned,  # velocity NED
            0, 0, 0,  # acceleration
            0, 0,  # yaw, yaw_rate
        )

    def send_acceleration(self, ax_ned, ay_ned, az_ned):
        """Send acceleration setpoint in NED frame (az positive = down).
        PX4 expects desired linear acceleration (gravity compensation is automatic).
        """
        self.fc.mav.set_position_target_local_ned_send(
            0,
            self.fc.target_system, self.fc.target_component,
            mavutil_module.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000110100111111,  # accel XY only mask (ignore pos, vel, yaw, accel Z for altitude hold)
            0, 0, 0,  # position
            0, 0, 0,  # velocity
            ax_ned, ay_ned, az_ned,  # acceleration NED
            0, 0,  # yaw, yaw_rate
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


# We import mavutil lazily to avoid import errors
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
                        if k not in ("depth_frame", "depth_colored")}
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
            if "target" in data:
                AVOIDANCE_TARGET = np.array(data["target"], dtype=np.float32)
            with control_lock:
                control_cmd["start"] = True
            self._json_response({"ok": True, "target": AVOIDANCE_TARGET.tolist()})
        elif self.path == "/stop_auto":
            with control_lock:
                control_cmd["stop"] = True
            self._json_response({"ok": True})
        elif self.path == "/set_target":
            if "target" in data:
                AVOIDANCE_TARGET = np.array(data["target"], dtype=np.float32)
            self._json_response({"ok": True, "target": AVOIDANCE_TARGET.tolist()})
        elif self.path == "/set_target_forward":
            # Set target 5m ahead of drone based on current yaw and position
            with state_lock:
                cur_pos = shared_state.get("pose", {"x":0,"y":0,"z":0})
                cur_yaw = cur_pos.get("yaw", 0)
            fwd_x = np.cos(cur_yaw)
            fwd_y = np.sin(cur_yaw)
            dist = 5.0
            AVOIDANCE_TARGET = np.array([
                cur_pos["x"] + fwd_x * dist,
                cur_pos["y"] + fwd_y * dist,
                max(cur_pos["z"] + 0.5, 1.5),
            ], dtype=np.float32)
            print(f"[TARGET] Set forward: pos=({cur_pos['x']:.2f},{cur_pos['y']:.2f}) yaw={cur_yaw*57.3:.1f}deg -> target={AVOIDANCE_TARGET}")
            self._json_response({"ok": True, "target": AVOIDANCE_TARGET.tolist()})
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
    import cv2

    # --- Camera ---
    pipeline = None
    try:
        import pyrealsense2 as rs
        for w, h, fps in [(640, 480, 30), (1280, 720, 30)]:
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
    except Exception as e:
        print(f"[Camera] FAILED: {e}")

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
                policy = UpstreamAvoidancePolicy(p)
                break
            except Exception as e:
                print(f"[Policy] Failed to load {p}: {e}")
    if policy is None:
        print("[Policy] WARNING: no upstream_avoidance.onnx found, control will not work")

    # --- Flight Controller ---
    fc = None
    px4 = None
    try:
        from pymavlink import mavutil
        mavutil_module = mavutil
        fc = mavutil.mavlink_connection("/dev/ttyACM0", baud=921600)
        fc.wait_heartbeat(timeout=5)
        px4 = PX4Controller(fc)
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

    print("[LOOP] Starting main loop...")
    while True:
        try:
            t0 = time.time()

            # --- Get depth ---
            depth = None
            depth_source = "real"
            if pipeline:
                try:
                    frames = pipeline.wait_for_frames(1000)
                    depth_frame = frames.get_depth_frame()
                    if depth_frame:
                        depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
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

            # Colorize depth
            depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
            depth_vis = (depth_vis * 255).astype(np.uint8)
            depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

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
                            new_pos = np.array([msg.x, msg.y, -msg.z])  # convert to NEU
                            new_vel = np.array([msg.vx, msg.vy, -msg.vz])
                            if np.linalg.norm(new_pos - fc_pos) < 2.0:
                                fc_pos = new_pos
                                fc_vel = new_vel
                                fc_pos_filtered = 0.85 * fc_pos_filtered + 0.15 * fc_pos
                            pos = fc_pos_filtered.copy()
                            vel = fc_vel.copy()
                        elif mt == "HEARTBEAT":
                            fc_armed = bool(msg.base_mode & mavutil_module.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                            armed = fc_armed
                            cm = msg.custom_mode
                            main_mode = (cm >> 16) & 0xFF
                            px4_modes = {1:"MANUAL",2:"ALTCTL",3:"POSCTL",4:"AUTO",5:"ACRO",6:"OFFBOARD",7:"STABILIZED",8:"RATTITUDE"}
                            fc_mode_str = px4_modes.get(main_mode, f"MODE_{main_mode}")
                            fc_mode = fc_mode_str
                        elif mt == "SYS_STATUS":
                            fc_battery = msg.voltage_battery / 1000.0
                            battery = fc_battery
                except Exception:
                    pass
            if time.time() - fc_last_msg_time > 2.0:
                fc_mode = "失联" if fc else "无飞控"

            # --- Auto control state machine ---
            with control_lock:
                cmd_start = control_cmd["start"]
                cmd_stop = control_cmd["stop"]
                control_cmd["start"] = False
                control_cmd["stop"] = False

            if cmd_stop and auto_active:
                print("[AUTO] Stop requested -> switching to POSCTL")
                if px4:
                    px4.set_mode_posctl()
                auto_active = False
                auto_state = AUTO_IDLE
                if policy:
                    policy.reset()

            if cmd_start and not auto_active:
                if armed:
                    print(f"[AUTO] Start requested -> switching to OFFBOARD, target={AVOIDANCE_TARGET}")
                    if px4 and fc:
                        # Send zero ACCELERATION setpoints before switching (PX4 requirement)
                        # Must match the setpoint type used in main loop
                        for _ in range(20):
                            px4.send_acceleration(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        # Wait and verify OFFBOARD mode engaged
                        offboard_ok = False
                        for _ in range(20):
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb:
                                    mode_flag = hb.custom_mode >> 16
                                    if mode_flag == 6:  # OFFBOARD
                                        offboard_ok = True
                                        break
                            except:
                                pass
                        if offboard_ok:
                            auto_active = True
                            auto_state = AUTO_ACTIVE
                            if policy:
                                policy.reset()
                            print("[AUTO] OFFBOARD confirmed, policy control started")
                        else:
                            print("[AUTO] WARNING: OFFBOARD not confirmed, check FC mode")
                            auto_active = True  # still try, user can override with RC
                            auto_state = AUTO_ACTIVE
                            if policy:
                                policy.reset()
                else:
                    print(f"[AUTO] Start rejected: not armed (armed={armed})")

            # Update auto_state for display
            if not auto_active:
                if armed:
                    auto_state = AUTO_READY
                else:
                    auto_state = AUTO_IDLE

            # --- Run policy (always, for display; send commands only if active) ---
            accel_body = np.zeros(3)
            vpred_body = np.zeros(3)
            accel_world_neu = np.zeros(3)
            net_accel_neu = np.zeros(3)
            accel_setpoint_ned = np.zeros(3)
            debug_target_body = np.zeros(3)
            debug_fwd = np.zeros(3)
            if policy:
                try:
                    # Continuous carrot: keep target 5m ahead of current pos/yaw
                    # so drone always flies forward and avoids obstacles
                    if auto_active:
                        fwd_x = np.cos(yaw)
                        fwd_y = np.sin(yaw)
                        carrot_dist = 5.0
                        AVOIDANCE_TARGET = np.array([
                            pos[0] + fwd_x * carrot_dist,
                            pos[1] + fwd_y * carrot_dist,
                            pos[2] + 0.5,
                        ], dtype=np.float32)

                    result = policy.infer(depth, pos, vel, yaw, AVOIDANCE_TARGET)
                    accel_body = result["accel_body"]
                    vpred_body = result["vpred_body"]
                    accel_world_neu = result["accel_world"]
                    vpred_world_neu = result["vpred_world"]
                    debug_target_body = result.get("target_v_body", np.zeros(3))
                    debug_fwd = result.get("fwd", np.zeros(3))

                    # Upstream control law (thr_est_error = 1.0 on real drone):
                    # act = (a_pred - v_pred - g_neu) * 1.0 + g_neu
                    #     = a_pred - v_pred  (g_neu cancels out exactly)
                    # This "act" is the NET acceleration (gravity excluded).
                    # PX4 OFFBOARD acceleration control also compensates gravity internally,
                    # so we send exactly this net acceleration. DO NOT add/subtract g.
                    net_accel_neu = accel_world_neu - vpred_world_neu

                    # --- Speed limiter: bleed off acceleration if over speed limit ---
                    MAX_SPEED = 1.0  # m/s
                    speed = float(np.linalg.norm(vel))
                    if speed > MAX_SPEED:
                        # Apply braking acceleration opposite to velocity
                        brake = min((speed - MAX_SPEED) * 3.0, 2.0)
                        vel_dir = vel / max(speed, 0.01)
                        net_accel_neu -= vel_dir * brake

                    # Limit acceleration
                    net_accel_neu = np.clip(net_accel_neu, -1.5, 1.5)

                    # Convert NEU -> NED for PX4 (z flips sign)
                    accel_setpoint_ned = np.array([
                        net_accel_neu[0],
                        net_accel_neu[1],
                        -net_accel_neu[2],
                    ])
                except Exception as e:
                    print(f"[POLICY] Inference error: {e}")
                    traceback.print_exc()

            # Send acceleration setpoint only if auto control active
            if auto_active and px4 and fc:
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
                shared_state["pose"] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2]),
                                        "roll": float(roll), "pitch": float(pitch), "yaw": float(yaw)}
                shared_state["velocity"] = {"x": float(vel[0]), "y": float(vel[1]), "z": float(vel[2])}
                shared_state["policy_action"] = {"ax": float(accel_body[0]), "ay": float(accel_body[1]), "az": float(accel_body[2])}
                shared_state["policy_vpred"] = {"vx": float(-vpred_body[0]), "vy": float(-vpred_body[1]), "vz": float(vpred_body[2])}  # unflipped for display
                shared_state["velocity_setpoint"] = {"vx": float(net_accel_neu[0]), "vy": float(net_accel_neu[1]), "vz": float(net_accel_neu[2])}
                shared_state["accel_setpoint_ned"] = {"ax": float(accel_setpoint_ned[0]), "ay": float(accel_setpoint_ned[1]), "az": float(accel_setpoint_ned[2])}
                shared_state["target"] = {"x": float(AVOIDANCE_TARGET[0]), "y": float(AVOIDANCE_TARGET[1]), "z": float(AVOIDANCE_TARGET[2])}
                shared_state["debug_target_body"] = {"x": float(debug_target_body[0]), "y": float(debug_target_body[1]), "z": float(debug_target_body[2])}
                shared_state["debug_fwd"] = {"x": float(debug_fwd[0]), "y": float(debug_fwd[1]), "z": float(debug_fwd[2])}
                shared_state["auto_state"] = auto_state
                shared_state["auto_enabled"] = auto_active
                shared_state["status"] = (f"帧数={frame_count} | 解锁={'是' if armed else '否'} 模式={fc_mode} | "
                                          f"自动={'ON' if auto_active else 'OFF'} | "
                                          f"位置=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) 航向={yaw*57.3:.1f}° | "
                                          f"净加速度=({net_accel_neu[0]:.2f},{net_accel_neu[1]:.2f},{net_accel_neu[2]:.2f}) m/s² | "
                                          f"深度有效={valid_ratio*100:.0f}%")
                shared_state["fps"] = fps
                shared_state["depth_valid_ratio"] = valid_ratio
                shared_state["depth_source"] = depth_source
                shared_state["battery"] = battery
                shared_state["armed"] = armed
                shared_state["fc_mode"] = fc_mode
                shared_state["frame_count"] = frame_count

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"[LOOP] frame={frame_count} fps={fps} auto={auto_state} "
                      f"pos=({pos[0]:.2f},{pos[1]:.2f},{pos[2]:.2f}) "
                      f"a_net=({net_accel_neu[0]:.2f},{net_accel_neu[1]:.2f},{net_accel_neu[2]:.2f}) "
                      f"a_body=({accel_body[0]:.2f},{accel_body[1]:.2f},{accel_body[2]:.2f})")

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
                    shared_state["pose"] = {"x":float(pos[0]),"y":float(pos[1]),"z":float(pos[2]),"roll":0.1*np.sin(t),"pitch":0.1*np.cos(t),"yaw":t}
                    shared_state["velocity"] = {"x":0.5*np.cos(t),"y":-0.5*np.sin(t),"z":0.1*np.cos(t*2)}
                    shared_state["policy_action"] = {"ax":3*np.cos(t),"ay":2*np.sin(t),"az":0.5*np.sin(t)}
                    shared_state["velocity_setpoint"] = {"vx":2*np.cos(t),"vy":1.5*np.sin(t),"vz":0.2*np.sin(t*2)}
                    shared_state["status"] = f"SIM frame={frame}"
                    shared_state["fps"] = 30
                    shared_state["depth_valid_ratio"] = 0.85
                    shared_state["battery"] = 12.4
                    shared_state["armed"] = True
                    shared_state["fc_mode"] = "OFFBOARD"
                    shared_state["auto_state"] = "ACTIVE"
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
