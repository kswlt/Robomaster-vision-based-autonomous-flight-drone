# D435 Stereo IR Timing Benchmark

Status: PASS.

- Configuration: left/right IR, 640×480 Y8 at 30 FPS; RGB, depth, and point cloud disabled.
- Duration: 60.000 s; 1799 synchronized frame sets.
- Left/right rate: 29.983 FPS.
- Timestamp domain: librealsense value `2` (`GLOBAL_TIME`); timestamps came from frame measurements, not host `now()`.
- Duplicate timestamps: 0 on both streams. Backward timestamps: 0 on both streams.
- Inter-frame mean/median/P95/P99/max: 33.301 / 33.301 / 33.303 / 33.305 / 33.309 ms on both streams.
- Left-right timestamp delta: 0.000 ms maximum.

The next Phase A task is to preserve these measurement timestamps in the capture interface and add CPU/RAM/peak-RSS collection before Pure Stereo VO deployment.
