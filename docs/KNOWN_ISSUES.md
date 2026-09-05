# Known Issues

## NET-001: Stale direct NX IPv4 address

- Status: FIXED
- Evidence: NX `enP8p1s0` is `10.42.0.2/24`; Windows USB GbE `10.42.0.70/24` reaches it at 1 ms and SSH works.
- Current conclusion: Do not use the former `10.33.154.71` address.

## HW-001: Attached RealSense is D435, not D435i

- Status: BLOCKED
- Evidence: PID `8086:0b07`, product D435, serial `943623021659`; six video nodes but no HID/IIO IMU nodes.
- Current conclusion: USB 3 video is present, but it cannot provide the IMU required for current VIO scope.
- Next step: Attach D435i and repeat enumeration, or explicitly approve D435 depth-only work.
