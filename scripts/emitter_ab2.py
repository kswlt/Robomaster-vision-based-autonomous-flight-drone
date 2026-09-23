#!/usr/bin/env python3
"""Controlled D430 IR-emitter A/B using pyrealsense2 hardware control + rclpy grab.

Stage 1: auto-exposure ON  -> compare mean brightness (auto-exposure may hide the
                             difference, which is itself the point).
Stage 2: auto-exposure OFF, fixed exposure -> brightness difference now reflects
                             illumination ONLY, i.e. the true projector contribution.
Also computes the pixel-wise difference image between OFF and ON, which localises
exactly what the projector illuminates.
"""
import os
import sys
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


def stats(a):
    lo = cv2.GaussianBlur(a, (0, 0), 3.0)
    hi = a - lo
    hf = float(np.sqrt((hi ** 2).mean()) / (a.std() + 1e-6))
    gx = cv2.Sobel(a, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(a, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    m = mag > np.percentile(mag, 90)
    ang = np.arctan2(gy[m], gx[m])
    h, _ = np.histogram(ang, bins=18, range=(-np.pi, np.pi))
    h = h / max(1, h.sum())
    iso = float(h.min() / (h.mean() + 1e-12))
    return dict(mean=float(a.mean()), std=float(a.std()),
                p50=float(np.percentile(a, 50)), p95=float(np.percentile(a, 95)),
                p99=float(np.percentile(a, 99)),
                sat=float(100.0 * (a >= 254).mean()),
                lap=float(cv2.Laplacian(a.astype(np.uint8), cv2.CV_64F).var()),
                hf=hf, iso=iso)


def fstats(tag, s):
    print('  %-30s mean=%7.2f std=%7.2f p50=%5.0f p95=%5.0f p99=%5.0f '
          'sat=%6.3f%% lapvar=%8.2f hf=%.4f iso=%.3f' % (
              tag, s['mean'], s['std'], s['p50'], s['p95'], s['p99'],
              s['sat'], s['lap'], s['hf'], s['iso']))


class Grab(Node):
    def __init__(self):
        super().__init__('dsh_ab')
        qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST)
        self.buf = {k: [] for k in TOPICS}
        for k, t in TOPICS.items():
            self.create_subscription(Image, t, lambda m, kk=k: self.buf[kk].append(m), qos)

    def clear(self):
        for k in self.buf:
            self.buf[k] = []

    def wait_frames(self, n=6, timeout=15.0):
        self.clear()
        t0 = time.time()
        while time.time() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.2)
            if all(len(v) >= n for v in self.buf.values()):
                return True
        return False

    def last(self):
        out = {}
        for k, v in self.buf.items():
            if not v:
                continue
            msg = v[-1]
            b = np.frombuffer(msg.data, dtype=np.uint8)
            img = b.reshape(msg.height, msg.width) if msg.step == msg.width \
                else b.reshape(msg.height, msg.step)[:, :msg.width]
            out[k] = img
        return out


def stereo_sensor():
    for d in rs.context().query_devices():
        for s in d.sensors:
            if 'Stereo' in s.get_info(rs.camera_info.name):
                return d, s
    return None, None


def read_hw(s):
    d = {}
    for o in s.get_supported_options():
        k = str(o).replace('option.', '')
        try:
            d[k] = s.get_option(o)
        except Exception:
            pass
    return d


def show_hw(tag, s):
    d = read_hw(s)
    keys = [k for k in d if any(t in k for t in ('emitter', 'laser', 'exposure', 'gain'))]
    print('  HW[%s]: %s' % (tag, {k: d[k] for k in sorted(keys)}))


def main():
    os.makedirs(OUT, exist_ok=True)
    dev, sen = stereo_sensor()
    if sen is None:
        print('FATAL: no Stereo Module sensor found (device busy?)')
        return 1
    print('device: %s sn=%s' % (dev.get_info(rs.camera_info.name),
                                dev.get_info(rs.camera_info.serial_number)))
    show_hw('initial', sen)

    rclpy.init()
    node = Grab()
    results = {}

    def capture(label):
        if not node.wait_frames(6):
            print('  !! no frames for %s' % label)
            return None
        imgs = node.last()
        out = {}
        for k, img in imgs.items():
            a = img.astype(np.float32)
            s = stats(a)
            fstats(label + '_' + k, s)
            cv2.imwrite(os.path.join(OUT, '%s_%s.png' % (label, k)), img)
            out[k] = (s, img)
        results[label] = out
        return out

    def set_emitter(on):
        try:
            sen.set_option(rs.option.emitter_enabled, 1 if on else 0)
            sen.set_option(rs.option.laser_power, 150 if on else 0)
            time.sleep(1.0)
            d = read_hw(sen)
            print('  set emitter=%s -> hw readback emitter_enabled=%s laser_power=%s' % (
                on, d.get('emitter_enabled'), d.get('laser_power')))
            return True
        except Exception as exc:
            print('  SET FAILED: %s' % exc)
            return False

    # ---------- Stage 1: auto exposure ON ----------
    print('\n===== STAGE 1: auto-exposure ON =====')
    try:
        sen.set_option(rs.option.enable_auto_exposure, 1)
        time.sleep(2.0)
    except Exception as exc:
        print('  AE set failed: %s' % exc)
    show_hw('stage1', sen)
    set_emitter(False)
    time.sleep(2.0)
    capture('S1_emitOFF')
    set_emitter(True)
    time.sleep(2.0)
    capture('S1_emitON')

    # ---------- Stage 2: fixed exposure ----------
    print('\n===== STAGE 2: auto-exposure OFF, fixed exposure=%d =====' % FIXED_EXPOSURE)
    try:
        sen.set_option(rs.option.enable_auto_exposure, 0)
        sen.set_option(rs.option.exposure, FIXED_EXPOSURE)
        time.sleep(2.0)
    except Exception as exc:
        print('  exposure set failed: %s' % exc)
    show_hw('stage2', sen)
    set_emitter(False)
    time.sleep(2.0)
    capture('S2_emitOFF')
    set_emitter(True)
    time.sleep(2.0)
    capture('S2_emitON')

    # ---------- pixel-wise difference ----------
    print('\n===== PIXEL-WISE DIFFERENCE (S2 ON - S2 OFF) =====')
    for k in TOPICS:
        off = results.get('S2_emitOFF', {}).get(k)
        on = results.get('S2_emitON', {}).get(k)
        if off is None or on is None:
            print('  %s: missing pair' % k)
            continue
        d = on[1].astype(np.float32) - off[1].astype(np.float32)
        print('  %s: mean_diff=%+.2f  p50=%+.1f p95=%+.1f p99=%+.1f  '
              'frac(>+20)=%.2f%%  frac(<-20)=%.2f%%' % (
                  k, d.mean(), np.percentile(d, 50), np.percentile(d, 95),
                  np.percentile(d, 99), 100.0 * (d > 20).mean(),
                  100.0 * (d < -20).mean()))
        vis = np.clip(d * 4 + 128, 0, 255).astype(np.uint8)
        cv2.imwrite(os.path.join(OUT, 'DIFF_%s.png' % k), vis)

    # ---------- restore ----------
    print('\n===== RESTORE =====')
    set_emitter(False)
    try:
        sen.set_option(rs.option.enable_auto_exposure, 1)
        time.sleep(1.0)
    except Exception as exc:
        print('  AE restore failed: %s' % exc)
    show_hw('restored', sen)
    capture('S3_restored')

    node.destroy_node()
    rclpy.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
