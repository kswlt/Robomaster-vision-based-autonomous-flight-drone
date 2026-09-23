#!/usr/bin/env python3
"""Can the D430 IR emitter be reliably disabled, and does it depend on an open stream?

proj_sweep (camera node streaming) -> set 0, readback 0.0, image got darker.
precheck     (no stream)           -> set 0, readback 1.0.

This opens a real infra1/infra2 stream with pyrealsense2 (no ROS), then tries to
disable the emitter and verifies both the option state AND the actual image
response at fixed exposure.  That is the only combination that proves the
projector is really off rather than merely configured off.
"""
import time
import numpy as np
import pyrealsense2 as rs

W, H, FPS = 848, 480, 30


def sensor():
    for d in rs.context().query_devices():
        for s in d.sensors:
            try:
                if 'Stereo' in s.get_info(rs.camera_info.name):
                    return d, s
            except Exception:
                pass
    return None, None


def opts(s, keys):
    out = {}
    for o in s.get_supported_options():
        n = getattr(o, 'name', None) or str(o).replace('option.', '')
        if n in keys:
            out[n] = o
    return out


def read(s, o, name):
    try:
        return s.get_option(o[name])
    except Exception as e:
        return 'ERR:%s' % e


def setv(s, o, name, v):
    try:
        s.set_option(o[name], float(v))
        return True
    except Exception as e:
        print('      set %s=%s raised %r' % (name, v, e))
        return False


def main():
    dev, sen = sensor()
    if sen is None:
        raise SystemExit('no stereo sensor')
    names = {'emitter_enabled', 'laser_power', 'emitter_on_off', 'emitter_always_on',
             'enable_auto_exposure', 'exposure', 'gain', 'inter_cam_sync_mode'}
    o = opts(sen, names)
    print('=== before opening any stream ===')
    for k in sorted(o):
        print('  %-22s = %s' % (k, read(sen, o, k)))
    print('  try set emitter_enabled=0 (no stream):', setv(sen, o, 'emitter_enabled', 0))
    time.sleep(0.3)
    print('  readback (no stream)  :', read(sen, o, 'emitter_enabled'))
    print('  try set laser_power=0 (no stream)  :', setv(sen, o, 'laser_power', 0))
    time.sleep(0.3)
    print('  readback (no stream)  :', read(sen, o, 'laser_power'))

    print()
    print('=== opening infra1+infra2 %dx%d@%d with pyrealsense2 ===' % (W, H, FPS))
    cfg = rs.config()
    cfg.enable_stream(rs.stream.infrared, 1, W, H, rs.format.y8, FPS)
    cfg.enable_stream(rs.stream.infrared, 2, W, H, rs.format.y8, FPS)
    pipe = rs.pipeline()
    prof = pipe.start(cfg)
    time.sleep(1.5)
    # re-acquire the sensor handle: the one held before start() is stale
    dev2, sen2 = sensor()
    o2 = opts(sen2, names)
    print('  after start, options:')
    for k in sorted(o2):
        print('    %-22s = %s' % (k, read(sen2, o2, k)))

    def grab_stats(tag, n=20):
        imgs1, imgs2 = [], []
        for _ in range(n):
            fs = pipe.wait_for_frames(2000)
            i1 = fs.get_infrared_frame(1)
            i2 = fs.get_infrared_frame(2)
            if i1:
                imgs1.append(np.asanyarray(i1.get_data()).astype(np.float32))
            if i2:
                imgs2.append(np.asanyarray(i2.get_data()).astype(np.float32))
        a1 = np.mean(imgs1, axis=0) if imgs1 else np.zeros((H, W))
        a2 = np.mean(imgs2, axis=0) if imgs2 else np.zeros((H, W))
        print('    %-14s infra1 mean=%7.2f std=%6.2f | infra2 mean=%7.2f std=%6.2f'
              % (tag, a1.mean(), a1.std(), a2.mean(), a2.std()))
        return a1, a2

    print()
    print('=== A: force auto-exposure off + fixed exposure for a fair comparison ===')
    setv(sen2, o2, 'enable_auto_exposure', 0)
    setv(sen2, o2, 'exposure', 8500)
    time.sleep(1.5)
    print('    exposure readback :', read(sen2, o2, 'exposure'))

    print()
    print('=== B: with stream open, set laser_power=0 and emitter_enabled=0 ===')
    setv(sen2, o2, 'laser_power', 0)
    setv(sen2, o2, 'emitter_enabled', 0)
    time.sleep(1.5)
    print('    readback emitter_enabled =', read(sen2, o2, 'emitter_enabled'))
    print('    readback laser_power     =', read(sen2, o2, 'laser_power'))
    print('    readback emitter_on_off  =', read(sen2, o2, 'emitter_on_off'))
    print('    readback emitter_always_on =', read(sen2, o2, 'emitter_always_on'))
    off1, off2 = grab_stats('emitter OFF')

    print()
    print('=== C: with stream open, set laser_power=360 and emitter_enabled=1 ===')
    setv(sen2, o2, 'emitter_enabled', 1)
    setv(sen2, o2, 'laser_power', 360)
    time.sleep(1.5)
    print('    readback emitter_enabled =', read(sen2, o2, 'emitter_enabled'))
    print('    readback laser_power     =', read(sen2, o2, 'laser_power'))
    on1, on2 = grab_stats('emitter ON')

    print()
    print('=== D: response (ON minus OFF) at fixed exposure ===')
    d1 = on1 - off1
    d2 = on2 - off2
    print('    infra1 dmean=%+7.3f  dstd=%+.3f  frac(>+20)=%6.2f%%  frac(<-20)=%5.2f%%'
          % (d1.mean(), d1.std() - off1.std(), 100.0 * (d1 > 20).mean(), 100.0 * (d1 < -20).mean()))
    print('    infra2 dmean=%+7.3f  dstd=%+.3f  frac(>+20)=%6.2f%%  frac(<-20)=%5.2f%%'
          % (d2.mean(), d2.std() - off2.std(), 100.0 * (d2 > 20).mean(), 100.0 * (d2 < -20).mean()))

    print()
    print('=== E: restore, then leave the emitter OFF and confirm it persists ===')
    setv(sen2, o2, 'emitter_enabled', 0)
    setv(sen2, o2, 'laser_power', 0)
    time.sleep(1.0)
    print('    readback while streaming :', read(sen2, o2, 'emitter_enabled'),
          read(sen2, o2, 'laser_power'))

    print()
    print('=== F: stop the stream, then read back again ===')
    pipe.stop()
    time.sleep(1.0)
    dev3, sen3 = sensor()
    o3 = opts(sen3, names)
    print('    readback after stop, emitter_enabled =', read(sen3, o3, 'emitter_enabled'))
    print('    readback after stop, laser_power     =', read(sen3, o3, 'laser_power'))


if __name__ == '__main__':
    main()
