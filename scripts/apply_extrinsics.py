#!/usr/bin/env python3
"""Apply a camera pitch compensation (degrees about camera X axis) to
kalibr_imucam_chain.yaml on the board, and report the resulting matrices.
Usage: python3 apply_extrinsics.py <alpha_deg>
alpha negative => camera optical axis tilts down; positive => up.
Writes /home/orangepi/vio_ws/src/open_vins/config/d430/kalibr_imucam_chain.yaml
A backup of the nominal file is kept as kalibr_imucam_chain.nominal.yaml once.
"""
import numpy as np, sys, os, shutil

CFG = "/home/orangepi/vio_ws/src/open_vins/config/d430/kalibr_imucam_chain.yaml"
BAK = "/home/orangepi/vio_ws/src/open_vins/config/d430/kalibr_imucam_chain.nominal.yaml"

alpha = float(sys.argv[1])
a = np.radians(alpha)
Rx = np.array([[1,0,0],[0,np.cos(a),-np.sin(a)],[0,np.sin(a),np.cos(a)]])
R_IC = np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])
Rnew = R_IC @ Rx

def block(t):
    lines = []
    for i in range(3):
        lines.append("    - [{:.6f}, {:.6f}, {:.6f}, {:.3f}]".format(
            Rnew[i,0],Rnew[i,1],Rnew[i,2],t[i]))
    lines.append("    - [0.0, 0.0, 0.0, 1.0]")
    return "\n".join(lines)

if not os.path.exists(BAK):
    shutil.copy(CFG, BAK)
    print("backup saved:", BAK)

content = """%YAML:1.0

cam0:
  timeshift_cam_imu: -0.011
  T_imu_cam:
{b0}
  cam_overlaps: [1]
  camera_model: pinhole
  distortion_coeffs: [0.0, 0.0, 0.0, 0.0]
  distortion_model: radtan
  intrinsics: [422.21624755859375, 422.21624755859375, 423.2308349609375, 240.20713806152344]
  resolution: [848, 480]
  rostopic: /camera/camera/infra1/image_rect_raw

cam1:
  T_imu_cam:
{b1}
  cam_overlaps: [0]
  camera_model: pinhole
  distortion_coeffs: [0.0, 0.0, 0.0, 0.0]
  distortion_model: radtan
  intrinsics: [422.21624755859375, 422.21624755859375, 423.2308349609375, 240.20713806152344]
  resolution: [848, 480]
  rostopic: /camera/camera/infra2/image_rect_raw
""".format(b0=block([0.08,0.0,0.0]), b1=block([0.08,-0.05,0.0]))

open(CFG,"w").write(content)
print("applied alpha =", alpha, "deg")
print("optical axis in IMU:", np.round(Rnew @ np.array([0,0,1.]),4))
print(content)
