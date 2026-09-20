# -*- coding: utf-8 -*-
"""Complete the keyboard control feature in web_vis_board.py (backend loop + frontend JS)."""
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

# ---- 1. Backend: keyboard start/stop handling + velocity sending in main loop ----
rep(
    """            # Send setpoints
            if auto_active and px4 and fc:
                try:""",
    """            # --- Keyboard control ---
            global key_active
            if cmd_key_start and not auto_active and tag_state == TAG_IDLE and not key_active:
                if armed:
                    print("[KEY] Start keyboard control -> OFFBOARD")
                    if px4 and fc:
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok = False
                        for _ in range(20):
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb and (hb.custom_mode >> 16) == 6:
                                    offboard_ok = True
                                    break
                            except:
                                pass
                        key_active = True
                        print(f"[KEY] OFFBOARD confirmed={offboard_ok}")
                else:
                    print("[KEY] Start rejected: not armed")
            if cmd_key_stop and key_active:
                print("[KEY] Stop -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                key_active = False

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
                try:""",
    "backend loop keyboard handling",
)

# ---- 2. Backend: expose key_active in shared state (so UI stays in sync after refresh) ----
rep(
    """                shared_state["auto_state"] = auto_state
                shared_state["auto_enabled"] = auto_active""",
    """                shared_state["auto_state"] = auto_state
                shared_state["auto_enabled"] = auto_active
                shared_state["key_active"] = key_active""",
    "shared_state key_active",
)

# ---- 3. Frontend: read key_active from backend status ----
rep(
    """    const keyStatus = document.getElementById('key-status');
    if (keyStatus) {
      keyStatus.textContent = key_active ? '● 键盘控制中' : '未激活';
      keyStatus.className = 'auto-status ' + (key_active ? 'auto-active' : 'auto-idle');
    }""",
    """    const keyStatus = document.getElementById('key-status');
    if (keyStatus) {
      key_active = s.key_active;
      keyStatus.textContent = key_active ? '● 键盘控制中' : '未激活';
      keyStatus.className = 'auto-status ' + (key_active ? 'auto-active' : 'auto-idle');
    }""",
    "frontend key_active from status",
)

# ---- 4. Frontend: keyStart/keyStop/sendKeyUpdate functions + WASD listeners ----
rep(
    """let _tickCount = 0;""",
    """let key_active = false;
const KEY_SPEED = 0.5; // m/s
let keys = {};
async function keyStart() {
  await fetch('/key_start', {method:'POST'});
  key_active = true;
  updateKeyStatus();
}
async function keyStop() {
  await fetch('/key_stop', {method:'POST'});
  key_active = false;
  keys = {};
  sendKeyUpdate();
  updateKeyStatus();
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
document.addEventListener('keydown', function(e) {
  const k = e.key.toLowerCase();
  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = true;
    sendKeyUpdate();
    e.preventDefault();
  }
});
document.addEventListener('keyup', function(e) {
  const k = e.key.toLowerCase();
  if (['w','a','s','d',' ','q'].includes(k)) {
    keys[k] = false;
    sendKeyUpdate();
    e.preventDefault();
  }
});
let _tickCount = 0;""",
    "frontend keyboard functions + listeners",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done. Patched file written.")
