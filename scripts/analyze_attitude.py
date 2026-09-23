#!/usr/bin/env python3
"""Analyze VIO attitude (roll/pitch/yaw), accel bias, and position over time."""
import re, math, sys

lines = open('/tmp/vio.log', errors='ignore').read().splitlines()

pose_pat = re.compile(
    r'q_GtoI = ([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+) \| '
    r'p_IinG = ([-\d.]+),([-\d.]+),([-\d.]+)')
bias_pat = re.compile(r'ba = ([-\d.]+),([-\d.]+),([-\d.]+)')

rows = []
last_pose = None
for ln in lines:
    mp = pose_pat.search(ln)
    if mp:
        qx,qy,qz,qw = map(float, mp.group(1,2,3,4))
        px,py,pz = map(float, mp.group(5,6,7))
        last_pose = (qx,qy,qz,qw,px,py,pz)
        continue
    mb = bias_pat.search(ln)
    if mb and last_pose is not None:
        bax,bay,baz = map(float, mb.group(1,2,3))
        qx,qy,qz,qw,px,py,pz = last_pose
        roll = math.degrees(math.atan2(2*(qw*qx+qy*qz), 1-2*(qx*qx+qy*qy)))
        pitch = math.degrees(math.asin(max(-1,min(1,2*(qw*qy-qz*qx)))))
        yaw = math.degrees(math.atan2(2*(qw*qz+qx*qy), 1-2*(qy*qy+qz*qz)))
        rows.append((roll,pitch,yaw,px,py,pz,bax,bay,baz))
        last_pose = None

print(f"total samples: {len(rows)}")
if not rows:
    sys.exit(1)

n = len(rows)
step = max(1, n // 25)
print(f"{'roll':>8} {'pitch':>8} {'yaw':>8} {'pos_x':>8} {'pos_y':>8} {'pos_z':>8} {'ba_x':>8} {'ba_y':>8} {'ba_z':>8}")
for i in range(0, n, step):
    r = rows[i]
    print(f"{r[0]:8.2f} {r[1]:8.2f} {r[2]:8.2f} {r[3]:8.3f} {r[4]:8.3f} {r[5]:8.3f} {r[6]:8.4f} {r[7]:8.4f} {r[8]:8.4f}")
r = rows[-1]
print(f"{r[0]:8.2f} {r[1]:8.2f} {r[2]:8.2f} {r[3]:8.3f} {r[4]:8.3f} {r[5]:8.3f} {r[6]:8.4f} {r[7]:8.4f} {r[8]:8.4f}  <- latest")

pitches = [x[1] for x in rows]
baxs = [x[6] for x in rows]
print(f"\n--- summary ---")
print(f"pitch: initial={rows[0][1]:.3f} deg, final={rows[-1][1]:.3f} deg, max={max(pitches):.3f}, min={min(pitches):.3f}")
print(f"roll:  initial={rows[0][0]:.3f} deg, final={rows[-1][0]:.3f} deg")
print(f"ba_x:  initial={rows[0][6]:.4f}, final={rows[-1][6]:.4f}, max={max(baxs):.4f}")
g = 9.81
print(f"ba_x/g implies static tilt ~ {math.degrees(math.asin(max(-1,min(1,rows[-1][6]/g)))):.2f} deg")
