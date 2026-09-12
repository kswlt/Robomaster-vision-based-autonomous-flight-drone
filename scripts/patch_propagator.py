#!/usr/bin/env python3
"""给Propagator.cpp打补丁：低IMU频率兼容（扩展传播窗口50ms）"""
p = '/home/orangepi/vio_ws/src/open_vins/ov_msckf/src/state/Propagator.cpp'
with open(p) as f:
    s = f.read()

old = """    prop_data = Propagator::select_imu_readings(imu_data, time0, time1, false);
  }
  if (prop_data.size() < 2)
    return false;"""

new = """    prop_data = Propagator::select_imu_readings(imu_data, time0, time1, false);
  }
  if (prop_data.size() < 2) {
    // 低IMU频率兼容: 向前扩展窗口(50ms)再选一次, 避免odomimu断流
    std::lock_guard<std::mutex> lck2(imu_data_mtx);
    prop_data = Propagator::select_imu_readings(imu_data, time0 - 0.05, time1, false);
  }
  if (prop_data.size() < 2)
    return false;"""

assert old in s, 'pattern not found!'
s = s.replace(old, new)
with open(p, 'w') as f:
    f.write(s)
print('patched OK')
