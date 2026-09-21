# -*- coding: utf-8 -*-
"""Bug-fix bundle:
- auto/tag OFFBOARD switch: verify + keep-alive setpoints + fail-safe (no false activation)
- mutual exclusion: auto/tag start blocked while keyboard active
- speed: MAX_SPEED 1.5, ACCEL_LIMIT 2.0
- frontend: auto_reject/tag_reject feedback; /tag_land_start armed check
"""
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
    print("[ok] " + tag)

# 1. Speed config
rep(
    "MAX_SPEED = 1.0  # m/s",
    "MAX_SPEED = 1.5  # m/s\nACCEL_LIMIT = 2.0  # m/s^2 net accel clip for avoidance",
    "speed config",
)

# 2. shared_state reject fields
rep(
    '    "key_reject": "",\n}',
    '    "key_reject": "",\n    "auto_reject": "",\n    "tag_reject": "",\n}',
    "shared_state rejects",
)

# 3. auto start: verify OFFBOARD + keep-alive + fail-safe + mutual exclusion
rep(
    """            if cmd_start and not auto_active and tag_state == TAG_IDLE:
                if armed:
                    print(f"[AUTO] Start -> OFFBOARD avoidance")
                    if px4 and fc:
                        for _ in range(20):
                            px4.send_acceleration(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok = False
                        for _ in range(20):
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb:
                                    if (hb.custom_mode >> 16) == 6:
                                        offboard_ok = True
                                        break
                            except:
                                pass
                        auto_active = True
                        auto_state = AUTO_ACTIVE
                        if policy:
                            policy.reset()
                        print(f"[AUTO] OFFBOARD confirmed={offboard_ok}")""",
    """            if cmd_start and not auto_active and tag_state == TAG_IDLE and not key_active:
                if armed:
                    print(f"[AUTO] Start -> OFFBOARD avoidance")
                    if px4 and fc:
                        for _ in range(20):
                            px4.send_acceleration(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok = False
                        for _ in range(20):
                            px4.send_acceleration(0, 0, 0)
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb:
                                    if (hb.custom_mode >> 16) == 6:
                                        offboard_ok = True
                                        break
                            except:
                                pass
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
                        print(f"[AUTO] OFFBOARD confirmed={offboard_ok}")""",
    "auto start fail-safe",
)

# 4. auto stop clears reject
rep(
    """            if cmd_stop and auto_active:
                print("[AUTO] Stop requested -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                auto_active = False
                auto_state = AUTO_IDLE
                if policy:
                    policy.reset()""",
    """            if cmd_stop and auto_active:
                print("[AUTO] Stop requested -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                auto_active = False
                auto_state = AUTO_IDLE
                if policy:
                    policy.reset()
                with state_lock:
                    shared_state["auto_reject"] = ""
""",
    "auto stop clears reject",
)

# 5. tag start: verify OFFBOARD + keep-alive + fail-safe + mutual exclusion
rep(
    """            if cmd_tag_start and tag_state == TAG_IDLE and not auto_active:
                if armed:
                    print("[TAG] Tag landing start -> OFFBOARD")
                    if px4 and fc:
                        # Send zero velocity setpoints before switching
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        tag_state = TAG_SEARCH
                        tag_land_start_pos = pos.copy()
                        tag_last_detected_time = time.time()
                        print("[TAG] OFFBOARD engaged, entering SEARCH")""",
    """            if cmd_tag_start and tag_state == TAG_IDLE and not auto_active and not key_active:
                if armed:
                    print("[TAG] Tag landing start -> OFFBOARD")
                    if px4 and fc:
                        # Send zero velocity setpoints before switching
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                        px4.set_mode_offboard()
                        offboard_ok = False
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb and (hb.custom_mode >> 16) == 6:
                                    offboard_ok = True
                                    break
                            except:
                                pass
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
""",
    "tag start fail-safe",
)

# 6. tag stop clears reject
rep(
    """            if cmd_tag_stop and tag_state != TAG_IDLE and tag_state != TAG_LANDED:
                print("[TAG] Stop requested -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                tag_state = TAG_IDLE
                tag_land_start_pos = None""",
    """            if cmd_tag_stop and tag_state != TAG_IDLE and tag_state != TAG_LANDED:
                print("[TAG] Stop requested -> POSCTL")
                if px4:
                    px4.set_mode_posctl()
                tag_state = TAG_IDLE
                tag_land_start_pos = None
                with state_lock:
                    shared_state["tag_reject"] = ""
""",
    "tag stop clears reject",
)

# 7. key OFFBOARD confirm loop: keep-alive setpoints
rep(
    """                        offboard_ok = False
                        for _ in range(20):
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb and (hb.custom_mode >> 16) == 6:
                                    offboard_ok = True
                                    break
                            except:
                                pass
                        key_active = offboard_ok""",
    """                        offboard_ok = False
                        for _ in range(20):
                            px4.send_velocity_ned(0, 0, 0)
                            time.sleep(0.05)
                            try:
                                hb = fc.recv_match(type='HEARTBEAT', blocking=False)
                                if hb and (hb.custom_mode >> 16) == 6:
                                    offboard_ok = True
                                    break
                            except:
                                pass
                        key_active = offboard_ok""",
    "key confirm keep-alive",
)

# 8. accel clip constant
rep(
    "                    net_accel_neu = np.clip(net_accel_neu, -1.5, 1.5)",
    "                    net_accel_neu = np.clip(net_accel_neu, -ACCEL_LIMIT, ACCEL_LIMIT)",
    "accel clip constant",
)

# 9. /tag_land_start armed check
rep(
    """        elif self.path == "/tag_land_start":
            with control_lock:
                control_cmd["tag_land_start"] = True
            self._json_response({"ok": True})""",
    """        elif self.path == "/tag_land_start":
            with state_lock:
                armed_now = shared_state.get("armed", False)
            if not armed_now:
                self._json_response({"ok": False, "reason": "not armed", "msg": "飞机未解锁，请先遥控器解锁并起飞悬停"})
            else:
                with control_lock:
                    control_cmd["tag_land_start"] = True
                self._json_response({"ok": True, "msg": "开始 Tag 降落"})""",
    "tag_land_start armed check",
)

# 10. JS vars
rep(
    "let key_active = false;\nlet key_reject = '';",
    "let key_active = false;\nlet key_reject = '';\nlet auto_reject = '';\nlet tag_reject = '';",
    "js reject vars",
)

# 11. JS poll
rep(
    """      key_reject = s.key_reject || '';""",
    """      key_reject = s.key_reject || '';
      auto_reject = s.auto_reject || '';
      tag_reject = s.tag_reject || '';""",
    "js poll rejects",
)

# 12. JS auto-status shows reject
rep(
    """    autoStatus.textContent = {
      'IDLE': '等待起飞...',
      'READY': '✓ 已就绪',
      'ACTIVE': '● 自动避障中...',
      'STOPPING': '正在停止...'
    }[s.auto_state] || s.auto_state;
    autoStatus.className = 'auto-status auto-' + s.auto_state.toLowerCase();""",
    """    autoStatus.textContent = {
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
    }""",
    "js auto-status reject",
)

# 13. JS tag-status shows reject
rep(
    """    tagStatus.textContent = tagTexts[s.tag_state] || s.tag_state;
    tagStatus.className = 'tag-status tag-' + s.tag_state.replace('TAG_', '').toLowerCase();""",
    """    tagStatus.textContent = tagTexts[s.tag_state] || s.tag_state;
    if (s.tag_state === 'TAG_IDLE' && tag_reject) {
      tagStatus.textContent = '⚠ ' + tag_reject;
    }
    tagStatus.className = 'tag-status tag-' + s.tag_state.replace('TAG_', '').toLowerCase();""",
    "js tag-status reject",
)

# 14. JS startTagLand response feedback
rep(
    """async function startTagLand() {
  const resp = await fetch('/tag_land_start', {method:'POST'});
  const data = await resp.json();
  console.log('tag_land_start:', data);
}""",
    """async function startTagLand() {
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
}""",
    "js startTagLand feedback",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done.")
