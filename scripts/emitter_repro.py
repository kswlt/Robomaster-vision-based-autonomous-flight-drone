#!/usr/bin/env python3
"""Reproduce the precheck's emitter block exactly, with full instrumentation.

The standalone probe writes emitter_enabled=0 and reads back 0.0, but the same
operation inside vio_precheck.py read back 1.0.  This pinpoints which difference
matters (option-object identity, dict keys, ordering, or handle lifetime).
"""
import time
import pyrealsense2 as rs

print('=== step 1: acquire sensor exactly as the precheck does ===')
sen = None
for d in rs.context().query_devices():
    for s in d.sensors:
        try:
            if 'Stereo' in s.get_info(rs.camera_info.name):
                sen = s
        except Exception:
            pass
print('  sensor:', sen.get_info(rs.camera_info.name) if sen else None)

print('=== step 2: build the names dict exactly as the precheck does ===')
names = {}
for o in sen.get_supported_options():
    n = getattr(o, 'name', None) or str(o).replace('option.', '')
    names[n] = o
print('  keys containing "emitter":', [k for k in names if 'emitter' in k])
print('  keys containing "laser"  :', [k for k in names if 'laser' in k])
oe = names.get('emitter_enabled')
print('  names["emitter_enabled"] =', repr(oe))
try:
    print('  int(oe) =', int(oe))
except Exception as e:
    print('  int(oe) failed:', e)
try:
    print('  oe.name =', getattr(oe, 'name', None))
except Exception as e:
    print('  oe.name failed:', e)
try:
    print('  current =', sen.get_option(oe))
except Exception as e:
    print('  get_option failed:', e)

print('=== step 3: write 0 then read back (precheck ordering) ===')
try:
    if 'emitter_enabled' in names:
        sen.set_option(names['emitter_enabled'], 0.0)
        print('  set_option(emitter_enabled, 0.0) returned without raising')
    if 'laser_power' in names:
        sen.set_option(names['laser_power'], 0.0)
    time.sleep(0.5)
    ee = sen.get_option(names['emitter_enabled']) if 'emitter_enabled' in names else None
    lp = sen.get_option(names['laser_power']) if 'laser_power' in names else None
    print('  readback emitter_enabled =', ee)
    print('  readback laser_power     =', lp)
    print('  ee != 0.0 ->', ee != 0.0)
    print('  ee == 0.0 ->', ee == 0.0)
except Exception as exc:
    print('  EXCEPTION: %r' % exc)

print('=== step 4: enumerate ALL option values right now ===')
for o in sen.get_supported_options():
    n = getattr(o, 'name', None) or str(o).replace('option.', '')
    try:
        v = sen.get_option(o)
    except Exception as e:
        v = 'ERR'
    if 'emitter' in n or 'laser' in n:
        print('  %-24s = %s' % (n, v))
