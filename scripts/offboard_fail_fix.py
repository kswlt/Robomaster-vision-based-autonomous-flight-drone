# -*- coding: utf-8 -*-
"""Fix: OFFBOARD switch failure must NOT activate keyboard control; surface reason to frontend."""
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

# 1. shared_state: add key_reject field
rep(
    """    "tag_horizontal_error": 0.0,
}""",
    """    "tag_horizontal_error": 0.0,
    "key_reject": "",
}""",
    "shared_state key_reject",
)

# 2. Backend: key_active = offboard_ok; on failure revert to POSCTL + report reason
rep(
    """                        key_active = True
                        key_landing = False
                        print(f"[KEY] OFFBOARD confirmed={offboard_ok}")""",
    """                        key_active = offboard_ok
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
                        print(f"[KEY] OFFBOARD confirmed={offboard_ok}")""",
    "backend key_active=offboard_ok + reject reason",
)

# 3. key_stop clears reject
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
                with state_lock:
                    shared_state["key_reject"] = ""
""",
    "key_stop clears reject",
)

# 4. key_land clears reject
rep(
    """                key_active = False
                key_landing = True""",
    """                key_active = False
                key_landing = True
                with state_lock:
                    shared_state["key_reject"] = ""
""",
    "key_land clears reject",
)

# 5. JS: key_reject variable
rep(
    """let key_active = false;""",
    """let key_active = false;
let key_reject = '';""",
    "js key_reject var",
)

# 6. JS poll: pick up key_reject
rep(
    """      key_active = s.key_active;
      key_landing = s.key_landing;""",
    """      key_active = s.key_active;
      key_landing = s.key_landing;
      key_reject = s.key_reject || '';""",
    "js poll key_reject",
)

# 7. JS indicator: show reject reason
rep(
    """  if (key_landing) { line.textContent = '✈ 一键降落中（LAND 模式）'; return; }
  if (!key_active) { line.textContent = '未激活'; return; }""",
    """  if (key_landing) { line.textContent = '✈ 一键降落中（LAND 模式）'; return; }
  if (!key_active) {
    line.textContent = key_reject ? ('⚠ ' + key_reject) : '未激活';
    return;
  }""",
    "js indicator shows reject",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done.")
