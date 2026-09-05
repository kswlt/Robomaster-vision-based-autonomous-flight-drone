# Known Issues

## NET-001: Stale direct NX IPv4 address

- Status: FIXED
- Evidence: NX `enP8p1s0` is `10.42.0.2/24`; Windows USB GbE `10.42.0.70/24` reaches it at 1 ms and SSH works.
- Current conclusion: Do not use the former `10.33.154.71` address.

## HW-001: Camera model was previously documented incorrectly

- Status: FIXED
- Evidence: PID `8086:0b07`, product D435, serial `943623021659`; six video nodes and no HID/IIO IMU nodes.
- Current conclusion: D435 is the intended camera. Its lack of internal IMU is expected; PX4 supplies future VIO IMU data.

## ENV-001: librealsense runtime is unavailable from configured apt sources

- Status: INVESTIGATING
- Evidence: `rs-enumerate-devices` and RealSense runtime libraries are absent. `apt-cache search` only returns ROS wrapper packages, not `librealsense2-*` packages.
- Current conclusion: Do not install the ROS wrapper by itself. Evaluate a pinned, user-space librealsense build that excludes DKMS and BSP changes.
- Next step: Obtain user approval for that limited installation path.
