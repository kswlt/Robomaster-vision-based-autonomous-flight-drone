# Known Issues

## NET-001: Stale direct NX IPv4 address

- Status: FIXED
- Evidence: NX `enP8p1s0` is `10.42.0.2/24`; Windows USB GbE `10.42.0.70/24` reaches it at 1 ms and SSH works.
- Current conclusion: Do not use the former `10.33.154.71` address.

## HW-001: Camera model was previously documented incorrectly

- Status: FIXED
- Evidence: PID `8086:0b07`, product D435, serial `943623021659`; six video nodes and no HID/IIO IMU nodes.
- Current conclusion: D435 is the intended camera. Its lack of internal IMU is expected; PX4 supplies future VIO IMU data.

## ENV-001: No immediately usable librealsense runtime

- Status: INVESTIGATING
- Evidence: Configured apt sources only provide ROS wrappers, not `librealsense2-*`. A user-space RSUSB build of v2.58.4 succeeds, but `rs-enumerate-devices` cannot open raw USB because `/dev/bus/usb/*` is root-owned. V4L2 backend configuration did not finish due dependency fetch failure.
- Current conclusion: Do not install the ROS wrapper alone or modify udev permissions yet. Complete the no-root V4L2 build using locally staged dependencies.
- Next step: Stage the required third-party dependency from the Windows host and complete V4L2 build/validation.
