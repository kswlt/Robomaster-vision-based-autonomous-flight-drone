# D435 Foxglove Preview

- NX Wi-Fi: `192.168.1.53`; Foxglove Bridge: `ws://192.168.1.53:8765`.
- D435 topics: `/d435/infra1/image_raw`, `/d435/infra2/image_raw`.
- Preview: `/foxglove/d435/infra1/compressed`, 640×480 JPEG quality 70 at 5 Hz (measured 4.999 Hz).
- Windows: connect Foxglove Studio to `ws://192.168.1.53:8765`, then add an Image panel for the preview topic.
- RGB, depth, point cloud, PX4 commands, arm commands, and mode commands are not used.
- Formal source: `ros2_ws/src/d435_ros2_publisher`; temporary NX runtime: `/tmp/robomaster-d435-ros2-ws`.
