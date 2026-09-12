#!/usr/bin/env python3
"""给VioManager.cpp打补丁: ZUPT成功提前return时也更新timelastupdate, 保证odomimu持续发布"""
p = '/home/orangepi/vio_ws/src/open_vins/ov_msckf/src/core/VioManager.cpp'
with open(p) as f:
    s = f.read()

old = """    if (did_zupt_update) {
      assert(state->_timestamp == message.timestamp);
      propagator->clean_old_imu_measurements(message.timestamp + state->_calib_dt_CAMtoIMU->value()(0) - 0.10);"""

new = """    if (did_zupt_update) {
      assert(state->_timestamp == message.timestamp);
      timelastupdate = message.timestamp;
      propagator->clean_old_imu_measurements(message.timestamp + state->_calib_dt_CAMtoIMU->value()(0) - 0.10);"""

assert old in s, 'pattern not found!'
s = s.replace(old, new)
with open(p, 'w') as f:
    f.write(s)
print('patched OK')
