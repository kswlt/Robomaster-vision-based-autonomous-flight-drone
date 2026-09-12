#!/usr/bin/env python3
"""同时订阅IMU和图像，对比时间戳差（判断VIO不发布odom的根因）"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from sensor_msgs.msg import Image

class TimeCheck(Node):
    def __init__(self):
        super().__init__('time_check')
        self.imu_t = None
        self.img_t = None
        self.count = 0
        self.create_subscription(Imu, '/imu', self.icb, 100)
        self.create_subscription(Image, '/camera/camera/infra1/image_rect_raw', self.gcb, 100)
        self.create_timer(1.0, self.tick)

    def icb(self, m):
        self.imu_t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9

    def gcb(self, m):
        self.img_t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9

    def tick(self):
        if self.imu_t and self.img_t:
            self.count += 1
            diff = self.img_t - self.imu_t
            self.get_logger().info(
                f'[{self.count}] imu={self.imu_t:.6f} img={self.img_t:.6f} '
                f'img-imu={diff:+.3f}s')
            if self.count >= 8:
                self.get_logger().info('测试完成')
                rclpy.shutdown()

rclpy.init()
n = TimeCheck()
try:
    rclpy.spin(n)
except KeyboardInterrupt:
    pass
