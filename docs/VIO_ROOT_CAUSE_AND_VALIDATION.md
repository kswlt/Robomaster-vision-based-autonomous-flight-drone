# Authoritative VIO status

**ROOT CAUSE UNDER INVESTIGATION — NOT VERIFIED IN FLIGHT**

> **Handoff update 2026-09-24:** this file's detailed measurements below are
> the 2026-09-13 audit snapshot. The operator subsequently confirmed STATIC
> setup and a 124.56 s static bag was recorded. It contains >2 s sensor gaps,
> and only 118.25 s valid `/odomimu`, so it is NOT a passing 120 s baseline.
> It showed 9.99 mm peak position drift and 0.00169 m/s velocity RMS while
> always-ZUPT was active. A bridge clock trace suggests -0.927 ms/s lower-
> quantile trend across 181 s, but this is not proof of crystal drift. Current
> remote board state is UNKNOWN: SSH timed out on 2026-09-24. Read
> [HANDOFF_2026-09-24.md](HANDOFF_2026-09-24.md) first for current evidence,
> caveats, uncommitted scripts and next steps.

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

## Measured update, 2026-09-13 23:18 CST

First milestone pushed: `e7ffdb0`. No baseline estimator YAML was edited.
Runtime service now also directly logged the loaded zero offset (not only the
isolated-domain test). Installed diagnostic binary SHA256:
`ed0ebc39968acabc9591e7356622627341dd73eeb843f10cfc1d9d248b6ca257`.

Fast DDS SHM initialization stalled camera/bridge/OpenVINS in domain 42.
Backtrace identifies SharedMemTransport input-channel creation. Official
`fastdds shm clean` removed 430 zombie segments but did not restore startup.
UDP-only XML + ROS_LOCALHOST_ONLY=0 restored startup; XML restricts traffic to
127.0.0.1. The diagnostic transport is a temporary systemd override at
`/run/systemd/system/vio.service.d/90-vio-audit-transport.conf` and disappears
on reboot. Startup script now allows VIO_ROS_LOCALHOST_ONLY override, default 1.
This is an acquisition workaround, NOT a VIO drift fix or final transport choice.
See [Fast DDS UDP documentation](https://fast-dds.docs.eprosima.com/en/v2.14.7/fastdds/transport/udp/udp.html).

D430 SDK serial 938422073656, ASIC/USB descriptor serial 943623021659,
firmware 5.17.3.10, USB 5000M. `rs-enumerate-devices` exists under the ROS
environment (initial unsourced shell did not find it). Both actual 848×480
CameraInfo P intrinsics exactly match YAML; D=0, R=I. Right P includes
stereo translation. Physical camera-IMU extrinsics still unverified.

Immutable TIMING_ONLY bag (no operator motion labels):
`/home/orangepi/vio_data/20260913T151309_590262Z_TIMING_ONLY/bag`.
Requested 60 s, actual sensor span ~58 s because recorder discovery consumes
startup time. New recorder adds 5 s allowance; always gate actual bag duration.
Manifest/hashes/metadata and small results are committed; raw ~1.4 GB bag is not.

| Measured item | Result |
|---|---|
| Left count / average rate | 1736 / 29.941 Hz |
| Right count / average rate | 1719 / 29.648 Hz |
| Paired stereo skew | 1719 pairs, exactly 0 ns |
| Unmatched left frames | 17; pairing/dropout gate NOT PASS |
| IMU count / average rate | 11352 / 195.062 Hz |
| IMU dt std / P95 / P99 / max | 0.858 / 5.557 / 9.874 / 11.108 ms |
| Negative / duplicate sensor timestamps | 0 / 0 |
| Nearest camera–IMU distance P99, left | 3.638 ms; NOT offset calibration |

Separate 60 s exclusive serial inspection: 11607 samples, no SYSTEM_TIME;
arrival-minus-sensor variation relative to minimum: median 29.319 ms,
P95 54.111 ms, P99 57.060 ms, max 1156.811 ms. Includes initial serial backlog;
sample max gap 997.864 ms. Excluding first 10 s still gives relative spread
P95 45.804 ms / P99 48.405 ms / max 57.572 ms and slope -0.000920 s/s.
This is NOT measured absolute serial latency or proven oscillator drift.
The utility requested 100 Hz (historical code), but received ~200 Hz for most
of the run; ACK was not recorded. A controlled 200 Hz repeat and bridge-internal
arrival/sample/mapping trace remain required. Raw trace stays on board.

Watchdog was restored after measurement and caught another real estimator
health failure: **position variance 4.071 m²**, VIO_FATAL at 23:17:13.
It latched and stopped vio.service at 23:17:23. **Latch is preserved; service
is currently stopped**, watchdog active, PX4 vision never enabled.
Full logs preserved under `/home/orangepi/vio_data/20260913_runtime_fault/`.
Trajectory reached tens of metres, but there is no operator-labeled trajectory
for that interval, so no endpoint metric or root-cause claim is made.

Next physical prerequisite: place assembly on a stable surface with a textured
static view and confirm readiness for STATIC 120 s. Prepare sensor-only capture
separately from estimator/watchdog, preserving the flight fault latch; raw bag
can then be replayed with isolated estimator candidates. Do not silently clear
the latch or restart flight output. All dynamic gates and flight remain pending.
