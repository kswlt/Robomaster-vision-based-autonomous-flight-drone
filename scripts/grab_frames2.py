#!/usr/bin/env python3
"""抓取一帧红外图像保存PNG（诊断画面）"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import numpy as np
import cv2

class Grabber(Node):
    def __init__(self):
        super().__init__('grabber')
        self.done = 0
        self.create_subscription(Image, '/camera/camera/infra1/image_rect_raw', lambda m: self.cb(m, 'infra1'), 1)
        self.create_subscription(Image, '/camera/camera/infra2/image_rect_raw', lambda m: self.cb(m, 'infra2'), 1)

    def cb(self, m, name):
        if self.done >= 2:
            return
        arr = np.frombuffer(m.data, dtype=np.uint8).reshape(m.height, m.width)
        mean = float(arr.mean())
        std = float(arr.std())
        big = cv2.resize(arr, (m.width * 2, m.height * 2), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite('/tmp/%s_%dx%d.png' % (name, m.width, m.height), big)
        self.get_logger().info('saved %s %dx%d mean=%.1f std=%.1f' % (name, m.width, m.height, mean, std))
        self.done += 1
        if self.done >= 2:
            raise SystemExit(0)

rclpy.init()
g = Grabber()
try:
    while rclpy.ok():
        rclpy.spin_once(g, timeout_sec=1.0)
except SystemExit:
    pass
print('done')
