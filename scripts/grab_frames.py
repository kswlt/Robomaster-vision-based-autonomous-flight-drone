#!/usr/bin/env python3
"""抓取D430左右相机图像保存PNG（检查画面）"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import numpy as np
import cv2

class Grabber(Node):
    def __init__(self):
        super().__init__('grabber')
        self.imgs = {}
        self.create_subscription(Image, '/camera/camera/infra1/image_rect_raw', lambda m: self.cb(m, 'infra1'), 10)
        self.create_subscription(Image, '/camera/camera/infra2/image_rect_raw', lambda m: self.cb(m, 'infra2'), 10)

    def cb(self, m, name):
        if name in self.imgs:
            return
        arr = np.frombuffer(m.data, dtype=np.uint8).reshape(m.height, m.width)
        # 统计亮度
        mean = float(arr.mean())
        std = float(arr.std())
        # 放大2倍便于查看
        big = cv2.resize(arr, (m.width * 2, m.height * 2), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite('/tmp/%s_%dx%d.png' % (name, m.width, m.height), big)
        self.imgs[name] = True
        self.get_logger().info('saved %s %dx%d mean=%.1f std=%.1f' % (name, m.width, m.height, mean, std))
        if len(self.imgs) == 2:
            rclpy.shutdown()

rclpy.init()
g = Grabber()
try:
    rclpy.spin(g)
except KeyboardInterrupt:
    pass
print('done')
