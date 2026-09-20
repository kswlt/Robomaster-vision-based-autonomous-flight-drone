# -*- coding: utf-8 -*-
"""Fast-path optimization:
1) keyboard control: main loop decoupled from camera frame rate (poll non-blocking, cached frames, 50 Hz sends)
2) depth display throttled to every 3rd frame while keyboard control active
3) /start_auto synchronous armed check + frontend feedback (same UX as key_start)
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
    print(f"[ok] {tag}")

# 1. Cached frame vars before main loop
rep(
    """    tag_vel_prev = np.zeros(2)
    tag_dt = 0.033
    tag_land_start_pos = None

    print("[LOOP] Starting main loop...")""",
    """    tag_vel_prev = np.zeros(2)
    tag_dt = 0.033
    tag_land_start_pos = None
    last_depth = None
    last_color = None
    depth_colored = None
    disp_frame = 0

    print("[LOOP] Starting main loop...")""",
    "cached frame vars",
)

# 2. Camera read: fast path when key_active (non-blocking poll + cached frames)
rep(
    """            if pipeline:
                try:
                    frames = pipeline.wait_for_frames(1000)
                    depth_frame = frames.get_depth_frame()
                    ir_frame = frames.get_infrared_frame(1) if TAG_IR_STREAM else None

                    if depth_frame:
                        depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                    if ir_frame:
                        # IR stream is y8 (grayscale), convert to BGR for visualization
                        ir_gray = np.asanyarray(ir_frame.get_data())
                        color_image = cv2.cvtColor(ir_gray, cv2.COLOR_GRAY2BGR)
                except Exception:
                    pass""",
    """            if pipeline:
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
                                if ir_frame:
                                    last_ir_gray = np.asanyarray(ir_frame.get_data())
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
                            depth = last_depth
                        if ir_frame:
                            last_ir_gray = np.asanyarray(ir_frame.get_data())
                            last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)
                            color_image = last_color
                except Exception:
                    pass""",
    "fast path camera read",
)

# 3. Depth colorize throttled while key_active
rep(
    """            # Colorize depth
            depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
            depth_vis = (depth_vis * 255).astype(np.uint8)
            depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)""",
    """            # Colorize depth (throttled to every 3rd frame while keyboard control active)
            disp_frame += 1
            if (not key_active) or (disp_frame % 3 == 1) or depth_colored is None:
                depth_vis = np.clip(3.0 / np.clip(depth, 0.3, 24.0) - 0.6, 0, 1)
                depth_vis = (depth_vis * 255).astype(np.uint8)
                depth_colored = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)""",
    "depth display throttle",
)

# 4. Loop period: 20 ms (50 Hz) while key_active, else 33 ms
rep(
    """            elapsed = time.time() - t0
            if elapsed < 0.033:
                time.sleep(0.033 - elapsed)""",
    """            elapsed = time.time() - t0
            target_period = 0.02 if key_active else 0.033
            if elapsed < target_period:
                time.sleep(target_period - elapsed)""",
    "loop period 50Hz when key_active",
)

# 5. /start_auto synchronous armed check
rep(
    """        if self.path == "/start_auto":
            with control_lock:
                control_cmd["start"] = True
            self._json_response({"ok": True})""",
    """        if self.path == "/start_auto":
            with state_lock:
                armed_now = shared_state.get("armed", False)
            if not armed_now:
                self._json_response({"ok": False, "reason": "not armed", "msg": "飞机未解锁，请先遥控器解锁并起飞悬停"})
            else:
                with control_lock:
                    control_cmd["start"] = True
                self._json_response({"ok": True, "msg": "开始自动避障"})""",
    "/start_auto armed check",
)

# 6. Frontend startAuto feedback
rep(
    """async function startAuto() {
  const resp = await fetch('/start_auto', {method:'POST'});
  const data = await resp.json();
  console.log('start_auto:', data);
}""",
    """async function startAuto() {
  let data = {};
  try {
    const resp = await fetch('/start_auto', {method:'POST'});
    data = await resp.json().catch(() => ({}));
  } catch(e) { return; }
  if (!data.ok && data.msg) {
    const el = document.getElementById('auto-status');
    if (el) el.textContent = '⚠ ' + data.msg;
  }
}""",
    "startAuto feedback",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done. Patched file written.")
