# 视觉位姿 USB 测试桥

`tools/vision_mavlink_bridge.py` 将 `/orb_slam3/stereo/pose` 以 MAVLink `VISION_POSITION_ESTIMATE` 发送到同一条 PX4 USB 串口 `/dev/ttyACM0`，同时保留 `/imu/data` 发布。它不发送解锁、模式、起飞或执行器指令；检测到 PX4 armed 标志后会停止发送视觉位姿。

当前只发送位置，姿态字段为 NaN；坐标假设为“D435 正向、水平安装”：ORB 相机坐标 `(x右,y下,z前)` 映射为 PX4 NED `(north=z,east=x,down=y)`。在地面站确认轴向前，必须保持拆桨和未解锁。若相机安装方向不同，先修改外参映射，不能直接飞行。

启动前停止旧的 `imu_mavlink_bridge.py`，避免两个进程同时打开 `/dev/ttyACM0`：

```bash
source /opt/ros/humble/setup.bash
source /home/nvidia/robomaster_d435_ros2_ws/install/setup.bash
/home/nvidia/fly/vio_benchmark/venv/bin/python tools/vision_mavlink_bridge.py
```
