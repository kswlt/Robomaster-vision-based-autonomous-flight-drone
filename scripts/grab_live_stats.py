#!/usr/bin/env python3
"""Grab N live infra1/infra2 frames and characterise them.

Usage: grab_live.py <label> [n_frames]
Writes /tmp/grabimg/<label>_{infra1,infra2}.png and prints statistics.
"""
import os
import sys
import time
import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import Image

LABEL = sys.argv[1] if len(sys.argv) > 1 else 'x'
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
OUT = '/tmp/grabimg'
TOPICS = {'infra1': '/camera/camera/infra1/image_rect_raw',
          'infra2': '/camera/camera/infra2/image_rect_raw'}


def band_energy(a):
    """Ratio of high-frequency energy to total, plus gradient isotropy."""
    lo = cv2.GaussianBlur(a, (0, 0), 3.0)
    hi = a - lo
    hf_ratio = float(np.sqrt((hi ** 2).mean()) / (a.std() + 1e-6))
    gx = cv2.Sobel(a, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(a, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx ** 2 + gy ** 2)
    m = mag > np.percentile(mag, 90)
    ang = np.arctan2(gy[m], gx[m])
    hist, _ = np.histogram(ang, bins=18, range=(-np.pi, np.pi))
    hist = hist / max(1, hist.sum())
    # isotropy: 1.0 = perfectly uniform direction distribution (speckle-like)
    isotropy = float(hist.min() / (hist.mean() + 1e-12))
    return hf_ratio, isotropy


class Grab(Node):
    def __init__(self):
        super().__init__('dsh_grab')
        qos = QoSProfile(depth=10,
                         reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE,
                         history=HistoryPolicy.KEEP_LAST)
        self.frames = {k: [] for k in TOPICS}
        for key, topic in TOPICS.items():
            self.create_subscription(Image, topic,
                                     lambda m, k=key: self.frames[k].append(m), qos)

    def done(self):
        return all(len(v) >= N for v in self.frames.values())


def analyse(key, msg, label):
    buf = np.frombuffer(msg.data, dtype=np.uint8)
    if msg.step == msg.width:
        img = buf.reshape(msg.height, msg.width)
    else:
        img = buf.reshape(msg.height, msg.step)[:, :msg.width]
    a = img.astype(np.float32)
    lap = float(cv2.Laplacian(img, cv2.CV_64F).var())
    hf, iso = band_energy(a)
    k = cv2.blur(a, (9, 9))
    hot = float(((a - k) > 20).mean() * 100.0)
    print('  %-28s mean=%7.2f std=%7.2f p50=%5.0f p95=%5.0f p99=%5.0f '
          'sat>=254=%6.3f%% lapvar=%8.2f hf_ratio=%.4f isotropy=%.3f hot%%=%.3f' % (
              label + '_' + key, a.mean(), a.std(), np.percentile(a, 50),
              np.percentile(a, 95), np.percentile(a, 99),
              100.0 * (a >= 254).mean(), lap, hf, iso, hot))
    fn = os.path.join(OUT, '%s_%s.png' % (label, key))
    cv2.imwrite(fn, img)
    return dict(mean=float(a.mean()), std=float(a.std()), lap=lap, hf=hf,
                iso=iso, hot=hot)


def main():
    os.makedirs(OUT, exist_ok=True)
    rclpy.init()
    node = Grab()
    t0 = time.time()
    while time.time() - t0 < 25 and not node.done():
        rclpy.spin_once(node, timeout_sec=0.25)
    print('=== LABEL %s ===' % LABEL)
    for key in TOPICS:
        if not node.frames[key]:
            print('  NO FRAMES for %s' % key)
            continue
        st = [analyse(key, m, LABEL) for m in node.frames[key][:N]]
        means = [s['mean'] for s in st]
        print('      %s frame means: %s' % (key, ['%.2f' % v for v in means]))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
