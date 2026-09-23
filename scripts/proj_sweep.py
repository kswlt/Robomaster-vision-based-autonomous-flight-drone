#!/usr/bin/env python3
"""D430 IR projector characterisation, with a WORKING hardware readback.

1. enumerate every Stereo Module option and its current value (no silent except)
2. write a known value and read it back to prove writes take effect
3. sweep laser_power 0 -> 360 with FIXED exposure and measure the image response
"""
import os
import time
import numpy as np
import cv2
import pyrealsense2 as rs
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import Image

OUT = '/tmp/grabimg'
TOPICS = {'infra1': '/camera/camera/infra1/image_rect_raw',
          'infra2': '/camera/camera/infra2/image_rect_raw'}
FIXED_EXPOSURE = 8500


class Grab(Node):
    def __init__(self):
        super().__init__('dsh_proj')
        qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST)
        self.buf = {k: [] for k in TOPICS}
        for k, t in TOPICS.items():
            self.create_subscription(Image, t, lambda m, kk=k: self.buf[kk].append(m), qos)

    def wait_frames(self, n=8, timeout=15.0):
        for k in self.buf:
            self.buf[k] = []
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.2)
            if all(len(v) >= n for v in self.buf.values()):
                return True
        return False

    def stack(self):
        out = {}
        for k, v in self.buf.items():
            if not v:
                continue
            arrs = []
            for msg in v[-6:]:
                b = np.frombuffer(msg.data, dtype=np.uint8)
                img = b.reshape(msg.height, msg.width) if msg.step == msg.width \
                    else b.reshape(msg.height, msg.step)[:, :msg.width]
                arrs.append(img.astype(np.float32))
            out[k] = np.mean(arrs, axis=0)
        return out


def enum_options(s):
    out = []
    try:
        opts = s.get_supported_options()
    except Exception as exc:
        print('  get_supported_options FAILED: %r' % exc)
        return out
    print('  n_supported_options = %d' % len(opts))
    for o in opts:
        name = getattr(o, 'name', None)
        if name is None:
            name = str(o).replace('option.', '')
        val = 'UNREADABLE'
        try:
            val = s.get_option(o)
            out.append((name, val, o))
        except Exception as exc:
            val = 'ERR:%s' % exc
        print('    %-34s = %s' % (name, val))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    dev = None
    sen = None
    for d in rs.context().query_devices():
        for s in d.sensors:
            try:
                nm = s.get_info(rs.camera_info.name)
            except Exception:
                nm = '?'
            print('device %s sensor %s' % (d.get_info(rs.camera_info.name), nm))
            if 'Stereo' in nm:
                dev, sen = d, s
    if sen is None:
        print('FATAL no stereo sensor')
        return 1

    print('\n===== ALL STEREO MODULE OPTIONS (current values) =====')
    opts = enum_options(sen)
    by_name = {n: o for n, v, o in opts}
    print('  readable options: %d' % len(by_name))

    rclpy.init()
    node = Grab()

    def snap(label):
        if not node.wait_frames(8):
            print('  !! no frames')
            return None
        imgs = node.stack()
        res = {}
        for k, a in imgs.items():
            s = dict(mean=float(a.mean()), p95=float(np.percentile(a, 95)),
                     sat=float(100.0 * (a >= 254).mean()))
            res[k] = (s, a)
            print('    %-22s mean=%7.2f p95=%5.1f sat=%6.3f%%' % (
                label + '_' + k, s['mean'], s['p95'], s['sat']))
        return res

    def setopt(name, value):
        if name not in by_name:
            print('    %s: NOT SETTABLE (not in readable list)' % name)
            return None
        try:
            sen.set_option(by_name[name], float(value))
            time.sleep(0.6)
            rb = sen.get_option(by_name[name])
            print('    %s <- %s  readback=%s' % (name, value, rb))
            return rb
        except Exception as exc:
            print('    %s <- %s FAILED: %r' % (name, value, exc))
            return None

    # prove writes take effect on a harmless option
    print('\n===== WRITE-THEN-READ PROBE =====')
    for probe in ('enable_auto_exposure', 'exposure', 'gain', 'laser_power', 'emitter_enabled'):
        if probe in by_name:
            try:
                cur = sen.get_option(by_name[probe])
                print('  %s current=%s' % (probe, cur))
            except Exception as exc:
                print('  %s read failed %r' % (probe, exc))

    print('\n===== FIX EXPOSURE =====')
    setopt('enable_auto_exposure', 0)
    setopt('exposure', FIXED_EXPOSURE)

    print('\n===== LASER POWER SWEEP (fixed exposure) =====')
    base = None
    sweep = {}
    for lp in (0, 90, 150, 240, 360):
        print('  --- laser_power=%d, emitter_enabled=1 ---' % lp)
        setopt('emitter_enabled', 1)
        setopt('laser_power', lp)
        time.sleep(1.5)
        r = snap('LP%03d' % lp)
        if r is None:
            continue
        sweep[lp] = r
        for k, (s, a) in r.items():
            cv2.imwrite(os.path.join(OUT, 'LP%03d_%s.png' % (lp, k)), a.astype(np.uint8))
        if lp == 0:
            base = {k: v[1] for k, v in r.items()}

    if base:
        print('\n  === response vs laser_power=0 (fixed exposure) ===')
        for lp, r in sorted(sweep.items()):
            for k, (s, a) in r.items():
                d = a - base[k]
                print('    LP=%3d %-8s dmean=%+7.3f  dp95=%+7.1f  frac(>+20)=%6.2f%%  '
                      'frac(<-20)=%5.2f%%' % (
                          lp, k, d.mean(), np.percentile(d, 95) - np.percentile(base[k], 95),
                          100.0 * (d > 20).mean(), 100.0 * (d < -20).mean()))

    print('\n===== EMITTER_ENABLED=0 (laser_power=360) =====')
    setopt('laser_power', 360)
    setopt('emitter_enabled', 0)
    time.sleep(1.5)
    snap('EE0_LP360')

    print('\n===== RESTORE =====')
    setopt('emitter_enabled', 1)
    setopt('laser_power', 0)
    setopt('enable_auto_exposure', 1)
    time.sleep(1.0)
    print('  final option state:')
    enum_options(sen)

    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
