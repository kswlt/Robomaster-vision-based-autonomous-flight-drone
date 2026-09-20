# -*- coding: utf-8 -*-
"""Z-key one-touch landing: backend /key_land -> PX4 LAND, frontend Z key + landing indicator."""
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

# 1. control_cmd + key_landing flag
rep(
    """    "key_vx": 0.0,
    "key_vy": 0.0,
    "key_vz": 0.0,
}
key_active = False""",
    """    "key_vx": 0.0,
    "key_vy": 0.0,
    "key_vz": 0.0,
    "key_land": False,
}
key_active = False
key_landing = False""",
    "control_cmd key_land + flag",
)

# 2. POST /key_land endpoint (after /key_stop)
rep(
    """        elif self.path == "/key_stop":
            with control_lock:
                control_cmd["key_stop"] = True
            self._json_response({"ok": True})""",
    """        elif self.path == "/key_stop":
            with control_lock:
                control_cmd["key_stop"] = True
            self._json_response({"ok": True})
        elif self.path == "/key_land":
            with control_lock:
                control_cmd["key_land"] = True
            self._json_response({"ok": True, "msg": "一键降落"})""",
    "POST /key_land",
)

# 3. Read + reset key_land in main loop
rep(
    """                cmd_key_vx = control_cmd["key_vx"]
                cmd_key_vy = control_cmd["key_vy"]
                cmd_key_vz = control_cmd["key_vz"]
                control_cmd["start"] = False
                control_cmd["stop"] = False
                control_cmd["tag_land_start"] = False
                control_cmd["tag_land_stop"] = False
                control_cmd["key_start"] = False
                control_cmd["key_stop"] = False""",
    """                cmd_key_vx = control_cmd["key_vx"]
                cmd_key_vy = control_cmd["key_vy"]
                cmd_key_vz = control_cmd["key_vz"]
                cmd_key_land = control_cmd["key_land"]
                control_cmd["start"] = False
                control_cmd["stop"] = False
                control_cmd["tag_land_start"] = False
                control_cmd["tag_land_stop"] = False
                control_cmd["key_start"] = False
                control_cmd["key_stop"] = False
                control_cmd["key_land"] = False""",
    "main loop read/reset key_land",
)

# 4. global key_landing + handle land request + reset on key start
rep(
    """            # --- Keyboard control ---
            global key_active
            if cmd_key_start and not auto_active and tag_state == TAG_IDLE and not key_active:""",
    """            # --- Keyboard control ---
            global key_active
            global key_landing
            if cmd_key_start and not auto_active and tag_state == TAG_IDLE and not key_active:""",
    "global key_landing",
)
rep(
    """                        key_active = True
                        print(f"[KEY] OFFBOARD confirmed={offboard_ok}")""",
    """                        key_active = True
                        key_landing = False
                        print(f"[KEY] OFFBOARD confirmed={offboard_ok}")""",
    "reset key_landing on start",
)
rep(
    """            if cmd_key_stop and key_active:
                print("[KEY] Stop -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                key_active = False""",
    """            if cmd_key_stop and key_active:
                print("[KEY] Stop -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                key_active = False
            if cmd_key_land and key_active:
                print("[KEY] Land requested -> LAND")
                if px4:
                    px4.set_mode_land()
                key_active = False
                key_landing = True""",
    "main loop land handling",
)

# 5. shared_state: report key_landing
rep(
    """                shared_state["key_active"] = key_active
                shared_state["key_cmd"] = {"vx": float(cmd_key_vx), "vy": float(cmd_key_vy), "vz": float(cmd_key_vz)}""",
    """                shared_state["key_active"] = key_active
                shared_state["key_landing"] = key_landing
                shared_state["key_cmd"] = {"vx": float(cmd_key_vx), "vy": float(cmd_key_vy), "vz": float(cmd_key_vz)}""",
    "shared_state key_landing",
)

# 6. HTML: Z key description + indicator block
rep(
    """      <b>W</b>前 <b>S</b>后 <b>A</b>左 <b>D</b>右<br>
      <b>空格</b>上升 <b>Q</b>下降<br>
      速度 0.5 m/s，松开自动停
    </div>""",
    """      <b>W</b>前 <b>S</b>后 <b>A</b>左 <b>D</b>右<br>
      <b>空格</b>上升 <b>Q</b>下降 <b>Z</b>一键降落<br>
      速度 0.5 m/s，松开自动停
    </div>""",
    "html key legend Z",
)
rep(
    """      <div id="k-space" class="key-ind">空格↑</div>
      <div id="k-q" class="key-ind">Q↓</div>
    </div>""",
    """      <div id="k-space" class="key-ind">空格↑</div>
      <div id="k-q" class="key-ind">Q↓</div>
      <div id="k-z" class="key-ind">Z 降落</div>
    </div>""",
    "html key indicator Z",
)

# 7. JS: key_landing variable + status sync
rep(
    """let key_active = false;
const KEY_SPEED = 0.5; // m/s
let keys = {};""",
    """let key_active = false;
let key_landing = false;
const KEY_SPEED = 0.5; // m/s
let keys = {};""",
    "js key_landing var",
)
rep(
    """    const keyStatus = document.getElementById('key-status');
    if (keyStatus) {
      key_active = s.key_active;
      keyStatus.textContent = key_active ? '● 键盘控制中' : '未激活';
      keyStatus.className = 'auto-status ' + (key_active ? 'auto-active' : 'auto-idle');
    }""",
    """    const keyStatus = document.getElementById('key-status');
    if (keyStatus) {
      key_active = s.key_active;
      key_landing = s.key_landing;
      if (key_landing) {
        keyStatus.textContent = '● 降落中 (LAND)';
        keyStatus.className = 'auto-status auto-stopping';
      } else {
        keyStatus.textContent = key_active ? '● 键盘控制中' : '未激活';
        keyStatus.className = 'auto-status ' + (key_active ? 'auto-active' : 'auto-idle');
      }
    }""",
    "js status sync landing",
)

# 8. JS: updateKeyIndicator shows landing state
rep(
    """function updateKeyIndicator() {
  const line = document.getElementById('key-cmd-line');
  if (!line) return;
  const set = (id, on) => { const el = document.getElementById(id); if (el) el.className = 'key-ind' + (on ? ' on' : ''); };
  set('k-w', !!keys['w']); set('k-s', !!keys['s']); set('k-a', !!keys['a']); set('k-d', !!keys['d']);
  set('k-space', !!keys[' ']); set('k-q', !!keys['q']);
  if (!key_active) { line.textContent = '未激活'; return; }""",
    """function updateKeyIndicator() {
  const line = document.getElementById('key-cmd-line');
  if (!line) return;
  const set = (id, on) => { const el = document.getElementById(id); if (el) el.className = 'key-ind' + (on ? ' on' : ''); };
  set('k-w', !!keys['w']); set('k-s', !!keys['s']); set('k-a', !!keys['a']); set('k-d', !!keys['d']);
  set('k-space', !!keys[' ']); set('k-q', !!keys['q']);
  if (key_landing) { line.textContent = '✈ 一键降落中（LAND 模式）'; return; }
  if (!key_active) { line.textContent = '未激活'; return; }""",
    "js indicator landing state",
)

# 9. JS: keyStart resets landing (keydown Z already applied via _fix_keydown_z.py)
rep(
    """  if (data.ok) {
    key_active = true;
    updateKeyStatus();
    updateKeyIndicator();
  } else {""",
    """  if (data.ok) {
    key_active = true;
    key_landing = false;
    updateKeyStatus();
    updateKeyIndicator();
  } else {""",
    "js keyStart reset landing",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done. Patched file written.")
