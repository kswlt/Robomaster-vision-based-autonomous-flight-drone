#!/usr/bin/env python3
"""给ROS2Visualizer.cpp加odomimu发布诊断日志"""
p = '/home/orangepi/vio_ws/src/open_vins/ov_msckf/src/ros/ROS2Visualizer.cpp'
with open(p) as f:
    s = f.read()

old = """void ROS2Visualizer::visualize_odometry(double timestamp) {

  // Return if we have not inited and a second has passes
  if (!_app->initialized() || (timestamp - _app->initialized_time()) < 1)
    return;"""

new = """void ROS2Visualizer::visualize_odometry(double timestamp) {

  // [诊断] 打印odomimu不发布的原因(每5秒一次)
  {
    static double last_dbg = -1.0;
    if (timestamp - last_dbg > 5.0) {
      last_dbg = timestamp;
      printf("[odom-dbg] init=%d init_time=%.3f ts=%.3f diff=%.3f\\n",
             (int)_app->initialized(), _app->initialized_time(), timestamp,
             timestamp - _app->initialized_time());
    }
  }

  // Return if we have not inited and a second has passes
  if (!_app->initialized() || (timestamp - _app->initialized_time()) < 1)
    return;"""

assert old in s, 'pattern not found!'
s = s.replace(old, new)
with open(p, 'w') as f:
    f.write(s)
print('patched OK')
