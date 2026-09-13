# Frame conventions: code audit, physical validation pending

Convention: R_A_from_B converts vector coordinates from B to A.
T_A_from_B maps a point p_A=R_A_from_B*p_B+t_A_from_B.

PX4 HIGHRES_IMU FRD (forward, right, down) → bridge ROS IMU FLU
(forward, left, up):

```
R_FLU_from_FRD = diag(1,-1,-1)
omega_FLU = R_FLU_from_FRD * omega_FRD
accel_FLU = R_FLU_from_FRD * accel_FRD
```

Bridge applies this once at angular_velocity and linear_acceleration assignment.
This is a proper rotation (det=+1), not a reflection. No measured axis/sign
test has yet been performed. Specific force at rest should point up in the
level FLU IMU frame; magnitude should be near 9.81 m/s².

The existing cam0 YAML matrix maps camera optical C (right, down, forward)
to IMU I (FLU). Despite the potentially ambiguous name T_imu_cam, the parser
calls it T_CtoI and explicitly inverts it for the estimator state:

```
R_I_from_C = [ 0  0  1 ]     t_I_from_C0 = [0.08,0,0]^T
             [-1  0  0 ]     t_I_from_C1 = [0.08,-0.05,0]^T
             [ 0 -1  0 ]

R_C_from_I = transpose(R_I_from_C)
t_C_from_I = -R_C_from_I * t_I_from_C
```

Thus optical forward→IMU forward; optical right→IMU right (-FLU Y);
optical down→IMU down (-FLU Z). Loaded estimator values:
t_C0_from_I=(0,0,-0.08); t_C1_from_I=(-0.05,0,-0.08).
The 8 cm lever arm and mounting rotation remain uncalibrated assumptions.

For angular velocity, omega_C=R_C_from_I*omega_FLU. A physical positive FLU
yaw (+Z) maps to camera -Y; positive FLU roll (+X) maps to camera +Z;
positive FLU pitch (+Y) maps to camera -X. A visual relative rotation mapping
old image bearings into the new camera frame describes scene motion and must
be inverted to compare with camera body angular motion.

OpenVINS reports q_GtoI internally; do not directly treat it as I→G without
checking the ROS visualizer inversion. Its local world heading is initialized
arbitrarily without an external yaw reference. A full ENU/NED/PX4 yaw alignment
audit remains necessary before enabling vision transmission.

Validation required: labeled roll/pitch/yaw bag segments, six stationary
attitudes, camera-center rotation lever-arm residuals and formal camera-IMU
calibration. Code consistency is not physical mounting verification.
