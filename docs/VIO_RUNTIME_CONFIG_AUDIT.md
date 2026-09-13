# Runtime configuration audit — 2026-09-13

Status: ROOT CAUSE UNDER INVESTIGATION. Initial origin/d430 and checked-out
d430: `b89b761895962ede7ff794b00b774a9ee7d7dc9d`. Local checkout initially was
clean main; fetched and created tracking d430 without resetting any history.

## Observed values

| Item | Repository | Runtime file | Loaded evidence |
|---|---|---|---|
| calib_cam_timeoffset | false | false | online calibration disabled |
| cam0.timeshift_cam_imu | missing | missing | **0.000000000 seconds** |
| num_pts / FAST / max_msckf | 200 / 12 / 75 | 200 / 12 / 75 | config; not independently instrumented |
| ZUPT chi2 multiplier | 0.5 | **0.3** | config; not independently instrumented |
| ZUPT max velocity | 0.05 | **0.02** | config; not independently instrumented |
| ZUPT max disparity | 0.15 | **0.10** | config; not independently instrumented |
| ZUPT | always | always | config |
| camera intrinsics, both | 422.2162476,422.2162476,423.230835,240.207138 | same | startup log confirms; CameraInfo still unverified |
| distortion, both | zero | same | startup log confirms |
| bridge / startup script | tracked files | same text | command line sends vision=false |

Runtime config: `/home/orangepi/vio_ws/src/open_vins/config/d430/`.
Systemd `/etc/systemd/system/vio.service` executes
`/home/orangepi/start_vio_systemd.sh`; process command line explicitly uses
the estimator YAML in that directory. Bridge executes
`/home/orangepi/vio_ws/vio_bridge/vio_bridge_combined.py`.

Hash evidence: `results/vio_validation/runtime_hashes.json`. Windows checkout
CRLF accounts for byte differences except estimator YAML, whose three ZUPT
values differ above. Runtime settings were preserved, not overwritten.

## Direct load verification

Original startup verbosity INFO hides the existing DEBUG offset print.
Added INFO diagnostics and missing-fixed-offset warning to the executable;
no estimator equations or calibration parameters changed. Built on board
successfully (only existing obsolete tf2-header warning). Executed the installed
binary against the actual runtime YAML in isolated ROS domain 43, with no
sensor publishers or PX4 output. See `loaded_config_audit.log` and
`diagnostic_build.log` in results. This establishes what the rebuilt executable
loads; it does not retroactively read the old running process's memory.
The diagnostic run emitted ROS teardown errors on timeout, retained in evidence.

The loaded quaternion is I→C, translation is I origin in C; the YAML contains
the inverse transform C→I. Both cameras load q=(-0.5,0.5,-0.5,0.5),
p0=(0,0,-0.08), p1=(-0.05,0,-0.08). These are **not calibrated results**.

## Historical -11 ms claim

`git show 3c93dadb32e8eccc7dc1c794abb76aa90d367bd3` changes only
estimator_config.yaml: disables online time calibration, increases features,
MSCKF batch size and tracking frequency. It does not set timeshift_cam_imu.
Current runtime also lacks it. No available evidence establishes the origin
of -11 ms or proves a prior runtime-only setting. Configuration/claim mismatch
is confirmed; its contribution to dynamic divergence awaits same-bag A/B.

VioManagerOptions.h defaults to 0 and reads optional cam0.timeshift_cam_imu.
Propagator.cpp explicitly implements **t_imu = t_cam + offset** by adding
the offset to both propagation interval endpoints. Thus -11 ms samples IMU
11 ms earlier than the image header time. Nearest-message subtraction cannot
estimate this calibration.

## Additional runtime blockers

D430 8086:0ad4 enumerates at 5000M. `rs-enumerate-devices` is not installed
on PATH; firmware/current profile/CameraInfo require further verification.
ROS domain 42 newly launched nodes stalled before normal logging; image rate
probes did not produce valid Hz evidence. Domain 43 successfully loaded.
Watchdog logs show repeated ~186-second restarts due to bridge log mtime.
Temporarily stopped vio-watchdog.service to prevent audit interruption;
vision sending remains false. Runtime OpenVINS source has no .git directory,
so an upstream base must be established by file comparison, not claimed.
