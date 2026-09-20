# -*- coding: utf-8 -*-
"""Dashboard keyboard-visualization patch: live key indicator + command text + backend key_cmd report."""
import sys

F = "web_vis_board.py"
with open(F, "r", encoding="utf-8") as fh:
    c = fh.read()

fails = []

def rep(old, new, tag):
    global c
    if old not in c:
        fails.append(tag)
        return
    if c.count(old) > 1:
        fails.append(tag + " (multiple matches)")
        return
    c = c.replace(old, new)
    print(f"[ok] {tag}")

# 1. CSS for key indicators
rep(
    """  .auto-stopping { color: #f78166; background: #2d1600; }""",
    """  .auto-stopping { color: #f78166; background: #2d1600; }
  .key-ind { padding: 4px 10px; border: 1px solid #30363d; border-radius: 6px; font-size: 12px; color: #8b949e; background: #161b22; transition: all .1s; user-select: none; }
  .key-ind.on { border-color: #58a6ff; color: #fff; background: #1f6feb; box-shadow: 0 0 8px rgba(88,166,255,.5); }""",
    "css key-ind",
)

# 2. HTML: key command line + key indicators in keyboard panel
rep(
    """      <b>W</b>前 <b>S</b>后 <b>A</b>左 <b>D</b>右<br>
      <b>空格</b>上升 <b>Q</b>下降<br>
      速度 0.5 m/s，松开自动停
    </div>
  </div>""",
    """      <b>W</b>前 <b>S</b>后 <b>A</b>左 <b>D</b>右<br>
      <b>空格</b>上升 <b>Q</b>下降<br>
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
    </div>
    <div style="margin-top:6px;font-size:12px;color:#3fb950;">定高：光流｜不按空格/Q 自动保持当前高度</div>
  </div>""",
    "html key panel",
)

# 3. JS: updateKeyIndicator function after sendKeyUpdate
rep(
    """async function sendKeyUpdate() {
  if (!key_active) return;
  let vx = 0, vy = 0, vz = 0;
  if (keys['w']) vx += KEY_SPEED;
  if (keys['s']) vx -= KEY_SPEED;
  if (keys['d']) vy += KEY_SPEED;
  if (keys['a']) vy -= KEY_SPEED;
  if (keys[' ']) vz -= KEY_SPEED * 0.7; // up
  if (keys['q']) vz += KEY_SPEED * 0.7; // down
  await fetch('/key_update', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({vx, vy, vz})});
}""",
    """async function sendKeyUpdate() {
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
  if (!key_active) { line.textContent = '未激活'; return; }
  let parts = [];
  if (keys['w']) parts.push('前 0.5');
  if (keys['s']) parts.push('后 0.5');
  if (keys['a']) parts.push('左 0.5');
  if (keys['d']) parts.push('右 0.5');
  if (keys[' ']) parts.push('升 0.35');
  if (keys['q']) parts.push('降 0.35');
  line.textContent = parts.length ? '指令：' + parts.join(' + ') + ' m/s' : '悬停（光流定高）';
}""",
    "js updateKeyIndicator",
)

# 4. Call updateKeyIndicator on start/stop
rep(
    """async function keyStart() {
  await fetch('/key_start', {method:'POST'});
  key_active = true;
  updateKeyStatus();
}""",
    """async function keyStart() {
  await fetch('/key_start', {method:'POST'});
  key_active = true;
  updateKeyStatus();
  updateKeyIndicator();
}""",
    "js keyStart calls indicator",
)
rep(
    """async function keyStop() {
  await fetch('/key_stop', {method:'POST'});
  key_active = false;
  keys = {};
  sendKeyUpdate();
  updateKeyStatus();
}""",
    """async function keyStop() {
  await fetch('/key_stop', {method:'POST'});
  key_active = false;
  keys = {};
  sendKeyUpdate();
  updateKeyStatus();
  updateKeyIndicator();
}""",
    "js keyStop calls indicator",
)

# 5. Call updateKeyIndicator on keydown/keyup
rep(
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = true;
    sendKeyUpdate();
    e.preventDefault();
  }""",
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = true;
    sendKeyUpdate();
    updateKeyIndicator();
    e.preventDefault();
  }""",
    "js keydown calls indicator",
)
rep(
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = false;
    sendKeyUpdate();
    e.preventDefault();
  }""",
    """  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = false;
    sendKeyUpdate();
    updateKeyIndicator();
    e.preventDefault();
  }""",
    "js keyup calls indicator",
)

# 6. cmd-desc: keyboard first
rep(
    """    let cmdText = "<b>模式: " + s.auto_state + "</b>";
    if (s.tag_state !== 'TAG_IDLE') {
        cmdText += " | <b style='color:#f0883e'>降落: " + s.tag_state + "</b>";
    }
    cmdText += "<br>净指令: (" + sp.vx.toFixed(2) + ", " + sp.vy.toFixed(2) + ", " + sp.vz.toFixed(2) + ") m/s²";""",
    """    let cmdText = "<b>模式: " + s.auto_state + "</b>";
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
    }""",
    "cmd-desc keyboard first",
)

# 7. Backend: report key_cmd in shared state
rep(
    """                shared_state["key_active"] = key_active""",
    """                shared_state["key_active"] = key_active
                shared_state["key_cmd"] = {"vx": float(cmd_key_vx), "vy": float(cmd_key_vy), "vz": float(cmd_key_vz)}""",
    "backend key_cmd",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done. Patched file written.")
