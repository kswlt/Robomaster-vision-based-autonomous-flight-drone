#!/usr/bin/env python3
"""Why does emitter_enabled read back as 1.0 after setting it to 0?

proj_sweep.py (camera node running) saw `emitter_enabled <- 0 readback=0.0`.
The precheck (no camera node) sees readback=1.0.  This isolates the difference:
is the write rejected when no stream is open, does it need a settle delay, or is
the value re-derived from the active profile on each read?
"""
import time
import pyrealsense2 as rs

sen = None
dev = None
for d in rs.context().query_devices():
    for s in d.sensors:
        try:
            if 'Stereo' in s.get_info(rs.camera_info.name):
                sen, dev = s, d
        except Exception:
            pass
if sen is None:
    raise SystemExit('no Stereo Module found')

print('device :', dev.get_info(rs.camera_info.name), dev.get_info(rs.camera_info.serial_number))

names = {}
for o in sen.get_supported_options():
    n = getattr(o, 'name', None) or str(o).replace('option.', '')
    names[n] = o
print('readable options:', len(names))
for k in ('emitter_enabled', 'laser_power', 'emitter_on_off', 'emitter_always_on',
          'visual_preset', 'enable_auto_exposure', 'exposure', 'gain'):
    if k in names:
        try:
            print('  %-22s = %s' % (k, sen.get_option(names[k])))
        except Exception as e:
            print('  %-22s = ERR %s' % (k, e))

if 'emitter_enabled' in names:
    opt = names['emitter_enabled']
    print()
    print('=== write 0, then read immediately and after delays ===')
    try:
        sen.set_option(opt, 0.0)
        for d in (0.0, 0.1, 0.5, 1.0, 2.0, 5.0):
            time.sleep(d if d else 0)
            try:
                print('  after %5.1fs : %s' % (d, sen.get_option(opt)))
            except Exception as e:
                print('  after %5.1fs : ERR %s' % (d, e))
    except Exception as e:
        print('  set_option raised: %r' % e)

    print()
    print('=== does the value depend on querying the device again? ===')
    for d2 in rs.context().query_devices():
        for s2 in d2.sensors:
            try:
                if 'Stereo' in s2.get_info(rs.camera_info.name):
                    o2 = None
                    for o in s2.get_supported_options():
                        n = getattr(o, 'name', None) or str(o).replace('option.', '')
                        if n == 'emitter_enabled':
                            o2 = o
                    if o2 is not None:
                        print('  fresh handle readback :', s2.get_option(o2))
            except Exception as e:
                print('  ERR', e)
