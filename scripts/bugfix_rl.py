# -*- coding: utf-8 -*-
"""RL control fixes:
1) net_accel = accel only (drop the dimensionally-wrong -vpred term)
2) DEPTH_ROTATE config (0/180) applied to depth+IR so image orientation can be corrected if needed
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

# 1. Config: DEPTH_ROTATE
rep(
    "ACCEL_LIMIT = 2.0  # m/s^2 net accel clip for avoidance",
    "ACCEL_LIMIT = 2.0  # m/s^2 net accel clip for avoidance\nDEPTH_ROTATE = 0   # 0 = no rotation; 180 = rotate depth/IR 180 deg if dashboard image is upside-down",
    "DEPTH_ROTATE config",
)

# 2. Normal path: rotate depth+IR
rep(
    """                        if depth_frame:
                            last_depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                            depth = last_depth
                        if ir_frame:
                            last_ir_gray = np.asanyarray(ir_frame.get_data())
                            last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)
                            color_image = last_color""",
    """                        if depth_frame:
                            last_depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                            if DEPTH_ROTATE == 180:
                                last_depth = cv2.rotate(last_depth, cv2.ROTATE_180)
                            depth = last_depth
                        if ir_frame:
                            last_ir_gray = np.asanyarray(ir_frame.get_data())
                            if DEPTH_ROTATE == 180:
                                last_ir_gray = cv2.rotate(last_ir_gray, cv2.ROTATE_180)
                            last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)
                            color_image = last_color""",
    "normal path rotate",
)

# 3. Fast path: rotate depth+IR
rep(
    """                                if depth_frame:
                                    last_depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                                if ir_frame:
                                    last_ir_gray = np.asanyarray(ir_frame.get_data())
                                    last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)""",
    """                                if depth_frame:
                                    last_depth = np.asanyarray(depth_frame.get_data()).astype(np.float32) / 1000.0
                                    if DEPTH_ROTATE == 180:
                                        last_depth = cv2.rotate(last_depth, cv2.ROTATE_180)
                                if ir_frame:
                                    last_ir_gray = np.asanyarray(ir_frame.get_data())
                                    if DEPTH_ROTATE == 180:
                                        last_ir_gray = cv2.rotate(last_ir_gray, cv2.ROTATE_180)
                                    last_color = cv2.cvtColor(last_ir_gray, cv2.COLOR_GRAY2BGR)""",
    "fast path rotate",
)

# 4. net_accel: drop -vpred (dimensionally wrong)
rep(
    "                    net_accel_neu = accel_world_neu - vpred_world_neu",
    "                    # Use the model's acceleration output directly as the command.\n"
    "                    # (Previously subtracted vpred - a velocity prediction in m/s - from\n"
    "                    # the acceleration in m/s^2, which polluted the setpoint.)\n"
    "                    net_accel_neu = accel_world_neu.copy()",
    "net_accel drop vpred",
)

if fails:
    print("FAILED PATCHES:", fails)
    sys.exit(1)

with open(F, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(c)
print("Done.")
