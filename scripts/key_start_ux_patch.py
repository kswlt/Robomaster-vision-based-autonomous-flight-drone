# -*- coding: utf-8 -*-
"""Improve key start UX: backend returns rejection reason synchronously; frontend shows it instead of flashing."""
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

# 1. Backend /key_start: check armed synchronously and return a clear reason
rep(
    """        elif self.path == "/key_start":
            with control_lock:
                control_cmd["key_start"] = True
            self._json_response({"ok": True})""",
    """        elif self.path == "/key_start":
            with state_lock:
                armed_now = shared_state.get("armed", False)
            if not armed_now:
                self._json_response({"ok": False, "reason": "not armed", "msg": "飞机未解锁，请先遥控器解锁并起飞悬停"})
            else:
                with control_lock:
                    control_cmd["key_start"] = True
                self._json_response({"ok": True, "msg": "开始键盘控制"})""",
    "backend /key_start armed check",
)

# 2. Frontend keyStart: act on the response instead of optimistic flash
rep(
    """async function keyStart() {
  await fetch('/key_start', {method:'POST'});
  key_active = true;
  updateKeyStatus();
  updateKeyIndicator();
}""",
    """async function keyStart() {
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
}""",
    "frontend keyStart handles rejection",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done. Patched file written.")
