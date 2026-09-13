# Authoritative VIO status

**ROOT CAUSE UNDER INVESTIGATION — NOT VERIFIED IN FLIGHT**

This document supersedes old status/hand-off claims. Initial Git HEAD:
`b89b761895962ede7ff794b00b774a9ee7d7dc9d` (d430). Subsequent milestone SHAs
are recorded in DEVELOPMENT_PROGRESS.md; use git log for this document's commit.

Confirmed: actual runtime YAML omits timeshift_cam_imu with online calibration
disabled; rebuilt executable loads **0 seconds**, not -0.011. Historical commit
does not contain the claimed fixed calibration. Three runtime ZUPT thresholds
also differ from Git. See [runtime audit](VIO_RUNTIME_CONFIG_AUDIT.md).
Neither discrepancy yet proves the complete cause of dynamic divergence.

Hardware: D430 PID 0ad4, 5000M observed; serial 938422073656 from handoff
(recording preflight verifies it). Firmware and actual image profile pending.
IMU: PX4 HIGHRES_IMU via bridge, boot-clock lower-envelope mapping;
rate/noise/jitter measurements pending. Camera parameters and 8 cm mount
translation are existing assumptions awaiting CameraInfo and physical calibration.

Time calibration: current loaded 0 s; **best offset unknown**, confidence and
stability unknown. Spatial calibration: unverified. IMU axis/sign: code review
pending physical verification. OpenVINS upstream base and patches: pending.
ZUPT: runtime always enabled, not accepted as final strategy. Frontend:
200/12/max_msckf 75, experimental; CPU 83% is historical, not this run's benchmark.

STATIC / ROTATION_ONLY / TRANSLATION / RECTANGLE: **NOT RUN**.
CPU/P95/P99: **NOT MEASURED**. Patched/upstream, EuRoC and independent backend:
**NOT RUN**. No valid immutable test bag exists at initial audit.

PX4: send_vision_to_px4=false verified in running command line; keep disabled
until all dynamic gates pass. No PX4 parameters changed; no arming/flight.

Next sequence: restore reliable sensor acquisition; immutable recordings;
all-sample timing analysis; visual/gyro offset scan; same-bag 0/-11/best A/B
with ZUPT off; calibration/frame/noise verification; ZUPT/frontend/patch A/B;
relative trajectory and latency gates. Only then evaluate PX4 integration.

Without external ground truth all hand-held trajectories are
**RELATIVE VALIDATION / NO EXTERNAL GROUND TRUTH**.
