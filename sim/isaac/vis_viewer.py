"""Standalone visualization viewer for E2E-RL policy demo.

Reads results/vis_data.npz written by demo_visualized.py (Isaac Sim process)
and displays a real-time OpenCV panel with:
  - Depth heatmap (what CNN sees)
  - State vector (10-dim)
  - Policy output (accel + yaw)
  - Flight trajectory top-down

Run this in a SEPARATE terminal from Isaac Sim:
    python sim/isaac/vis_viewer.py

Press 'q' or ESC to close.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import cv2

REPO_ROOT = Path(__file__).resolve().parents[2]
VIS_DATA_PATH = REPO_ROOT / "results" / "vis_data.npz"

W, H = 1200, 750
STATE_LABELS = [
    "local_vel_x", "local_vel_y", "local_vel_z",
    "target_x", "target_y", "target_z",
    "gravity_x", "gravity_y", "gravity_z",
    "margin",
]
ACTION_LABELS = ["accel_x", "accel_y", "accel_z", "yaw_rate", "thrust_mag", "(reserved)"]


def put_text(img, text, x, y, scale=0.5, color=(200, 200, 200), thickness=1):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_panel(img, x, y, w, h, title):
    cv2.rectangle(img, (x, y), (x + w, y + h), (60, 60, 70), 1)
    cv2.rectangle(img, (x, y), (x + w, y + 24), (45, 45, 60), -1)
    put_text(img, title, x + 8, y + 17, 0.5, (220, 220, 220), 1)


def main():
    print("=" * 60)
    print("E2E-RL Policy Visualization Viewer")
    print("=" * 60)
    print(f"Reading from: {VIS_DATA_PATH}")
    print("Waiting for Isaac Sim demo to start...")
    print("Press 'q' or ESC to close.\n")

    window_name = "E2E-RL Policy Visualization"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, W, H)

    last_mtime = 0
    last_data = None
    frame_count = 0

    while True:
        # Read data if file updated
        if VIS_DATA_PATH.exists():
            mtime = VIS_DATA_PATH.stat().st_mtime
            if mtime != last_mtime:
                try:
                    data = np.load(VIS_DATA_PATH, allow_pickle=True)
                    last_data = data
                    last_mtime = mtime
                except Exception:
                    pass  # File being written, skip this frame

        img = np.ones((H, W, 3), dtype=np.uint8) * 22

        # Title bar
        cv2.rectangle(img, (0, 0), (W, 36), (35, 35, 50), -1)
        put_text(img, "E2E-RL  Depth + DiffPhys CNN+GRU Policy  |  End-to-End Autonomous Impact",
                 15, 24, 0.6, (255, 255, 255), 1)

        if last_data is None:
            put_text(img, "Waiting for demo_visualized.py to start...", W // 2 - 200, H // 2, 0.7, (150, 150, 150))
            cv2.imshow(window_name, img)
            if cv2.waitKey(100) & 0xFF in (ord('q'), 27):
                break
            continue

        depth = last_data['depth']  # 48x64
        state = last_data['state']  # 10
        action = last_data['action']  # 6
        pos = last_data['pos']  # 3
        traj = last_data['trajectory']  # Nx2
        step = int(last_data['step'])
        episode = int(last_data['episode'])
        status = str(last_data['status'])
        hidden_norm = float(last_data['hidden_norm'])

        # --- Depth panel (top-left) ---
        dx, dy, dw, dh = 20, 50, 360, 280
        draw_panel(img, dx, dy, dw, dh, f"Depth Input  (64x48, inverse depth)")
        depth_vis = (np.clip(depth, 0, 1) * 255).astype(np.uint8)
        depth_bgr = cv2.applyColorMap(depth_vis, cv2.COLORMAP_VIRIDIS)
        depth_big = cv2.resize(depth_bgr, (dw - 20, dh - 50), interpolation=cv2.INTER_NEAREST)
        img[dy + 30:dy + 30 + depth_big.shape[0], dx + 10:dx + 10 + depth_big.shape[1]] = depth_big
        # Colorbar
        cb_x = dx + dw - 18
        for i in range(dh - 50):
            val = 1.0 - i / (dh - 50)
            c = cv2.applyColorMap(np.uint8([[val * 255]]), cv2.COLORMAP_VIRIDIS)[0, 0]
            cv2.line(img, (cb_x, dy + 30 + i), (cb_x + 10, dy + 30 + i), tuple(int(x) for x in c), 1)
        put_text(img, "near", cb_x - 28, dy + 42, 0.35, (160, 160, 160))
        put_text(img, "far", cb_x - 25, dy + dh - 14, 0.35, (160, 160, 160))
        put_text(img, "-> CNN Conv1(32) -> Conv2(64) -> Conv3(128)", dx + 10, dy + dh - 8, 0.38, (120, 200, 120))

        # --- State panel (top-middle) ---
        sx, sy, sw, sh = 400, 50, 360, 280
        draw_panel(img, sx, sy, sw, sh, "State Vector  (10-dim)")
        for i, label in enumerate(STATE_LABELS):
            val = state[i] if i < len(state) else 0
            yy = sy + 50 + i * 22
            # Label
            put_text(img, f"{label:14s}", sx + 12, yy, 0.42, (170, 170, 170))
            # Value
            put_text(img, f"{val:+8.3f}", sx + 160, yy, 0.42, (220, 220, 120))
            # Bar
            bar_max = 5.0
            bar_w = int(min(abs(val) / bar_max, 1.0) * 120)
            bar_color = (80, 180, 80) if val >= 0 else (80, 80, 180)
            cv2.rectangle(img, (sx + 235, yy - 10), (sx + 235 + bar_w, yy + 2), bar_color, -1)
        put_text(img, f"GRU hidden L2: {hidden_norm:.3f}", sx + 12, sy + sh - 12, 0.4, (150, 200, 255))

        # --- Action panel (top-right) ---
        ax, ay, aw, ah = 780, 50, 400, 280
        draw_panel(img, ax, ay, aw, ah, "Policy Output  (GRU -> Linear -> accel)")
        for i, label in enumerate(ACTION_LABELS):
            val = action[i] if i < len(action) else 0
            yy = ay + 50 + i * 22
            put_text(img, f"{label:14s}", ax + 12, yy, 0.42, (170, 170, 170))
            put_text(img, f"{val:+8.3f}", ax + 160, yy, 0.42, (255, 200, 100))
            bar_max = 10.0 if i < 3 else 3.0
            bar_w = int(min(abs(val) / bar_max, 1.0) * 150)
            bar_color = (255, 160, 60) if val >= 0 else (200, 100, 200)
            cv2.rectangle(img, (ax + 235, yy - 10), (ax + 235 + bar_w, yy + 2), bar_color, -1)
        # Arrow to drone
        put_text(img, "  |", ax + 12, ay + sh - 40, 0.4, (150, 150, 150))
        put_text(img, "  v", ax + 12, ay + sh - 25, 0.4, (150, 150, 150))
        put_text(img, "Drone dynamics -> Flight controller -> Motors", ax + 30, ay + sh - 25, 0.4, (120, 200, 120))

        # --- Trajectory panel (bottom, full width) ---
        tx, ty, tw, th = 20, 350, W - 40, 370
        draw_panel(img, tx, ty, tw, th, f"Flight Trajectory  (top-down)   Ep {episode}  Step {step}  Status: {status}")

        # World to pixel mapping
        x_min, x_max = -15, 15
        y_min, y_max = -8, 8
        plot_x = tx + 15
        plot_y = ty + 35
        plot_w = tw - 120
        plot_h = th - 55

        def w2p(wx, wy):
            px = plot_x + int((wx - x_min) / (x_max - x_min) * plot_w)
            py = plot_y + plot_h - int((wy - y_min) / (y_max - y_min) * plot_h)
            return px, py

        # Arena boundary
        corners = [w2p(-14, 7.5), w2p(14, 7.5), w2p(14, -7.5), w2p(-14, -7.5)]
        for i in range(4):
            cv2.line(img, corners[i], corners[(i + 1) % 4], (90, 90, 90), 2)

        # Grid
        for gx in range(-12, 13, 4):
            p1 = w2p(gx, -7.5)
            p2 = w2p(gx, 7.5)
            cv2.line(img, p1, p2, (40, 40, 40), 1)
        for gy in range(-6, 7, 3):
            p1 = w2p(-14, gy)
            p2 = w2p(14, gy)
            cv2.line(img, p1, p2, (40, 40, 40), 1)

        # HOME
        hp = w2p(-12, -6)
        cv2.circle(img, hp, 9, (0, 255, 0), -1)
        put_text(img, "HOME", hp[0] - 18, hp[1] - 14, 0.4, (0, 255, 0))

        # TARGET
        tp = w2p(3.08, 3.84)
        cv2.drawMarker(img, tp, (0, 80, 255), cv2.MARKER_STAR, 20, 2)
        cv2.circle(img, tp, 12, (0, 80, 255), 1)
        put_text(img, "ARMOR", tp[0] - 22, tp[1] - 18, 0.4, (0, 120, 255))

        # Trajectory
        if len(traj) > 1:
            for i in range(len(traj) - 1):
                p1 = w2p(float(traj[i, 0]), float(traj[i, 1]))
                p2 = w2p(float(traj[i + 1, 0]), float(traj[i + 1, 1]))
                alpha = i / len(traj)
                c = (int(60 + 180 * alpha), int(60 + 120 * alpha), 255)
                cv2.line(img, p1, p2, c, 2)

        # Current drone pos
        dp = w2p(float(pos[0]), float(pos[1]))
        cv2.circle(img, dp, 8, (0, 255, 255), -1)
        cv2.circle(img, dp, 12, (0, 255, 255), 1)
        put_text(img, f"DRONE ({pos[0]:.1f},{pos[1]:.1f},{pos[2]:.1f})", dp[0] + 14, dp[1] - 8, 0.4, (0, 255, 255))

        # Axis labels
        put_text(img, "X (m)", plot_x + plot_w // 2 - 15, ty + th - 8, 0.35, (100, 100, 100))
        put_text(img, "-15", plot_x, ty + th - 8, 0.3, (80, 80, 80))
        put_text(img, "+15", plot_x + plot_w - 22, ty + th - 8, 0.3, (80, 80, 80))
        put_text(img, "Y", plot_x - 14, plot_y + plot_h // 2, 0.3, (80, 80, 80))

        # Legend
        lx = tx + tw - 105
        put_text(img, "Legend:", lx, ty + 50, 0.4, (150, 150, 150))
        cv2.circle(img, (lx + 5, ty + 68), 5, (0, 255, 0), -1)
        put_text(img, "HOME", lx + 14, ty + 72, 0.35, (150, 150, 150))
        cv2.drawMarker(img, (lx + 5, ty + 88), (0, 80, 255), cv2.MARKER_STAR, 10, 1)
        put_text(img, "Armor", lx + 14, ty + 92, 0.35, (150, 150, 150))
        cv2.circle(img, (lx + 5, ty + 108), 5, (0, 255, 255), -1)
        put_text(img, "Drone", lx + 14, ty + 112, 0.35, (150, 150, 150))
        cv2.line(img, (lx, ty + 125), (lx + 12, ty + 125), (255, 100, 100), 2)
        put_text(img, "Path", lx + 14, ty + 129, 0.35, (150, 150, 150))

        # Status bar
        cv2.rectangle(img, (0, H - 28), (W, H), (30, 30, 40), -1)
        speed = np.linalg.norm(state[0:3]) if len(state) >= 3 else 0
        dist = np.linalg.norm(state[3:6]) if len(state) >= 6 else 0
        put_text(img, f"Speed: {speed:.2f} m/s   |   Dist to target: {dist:.2f} m   |   "
                       f"Altitude: {pos[2]:.2f} m   |   Frame: {frame_count}",
                 15, H - 10, 0.4, (140, 140, 140))

        cv2.imshow(window_name, img)
        frame_count += 1

        if cv2.waitKey(30) & 0xFF in (ord('q'), 27):
            break

    cv2.destroyAllWindows()
    print("Visualization viewer closed.")


if __name__ == "__main__":
    main()
