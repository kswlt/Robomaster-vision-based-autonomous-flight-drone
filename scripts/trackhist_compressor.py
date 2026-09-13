#!/usr/bin/env python3
"""
Compress /trackhist feature tracking visualization for low-latency Foxglove.
Subscribes to /trackhist (848x480 BGR8 ~10Hz), downsamples to 212x120,
throttles to 3Hz, publishes /trackhist_compressed.
Ultra-low bandwidth version (~0.3 Mbps).
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2


class TrackhistCompressor(Node):
    def __init__(self):
        super().__init__('trackhist_compressor')
        self.bridge = CvBridge()
        self.last_publish = 0.0
        self.publish_interval = 0.33  # ~3 Hz max
        self.target_width = 212
        self.target_height = 120

        self.sub = self.create_subscription(
            Image, '/trackhist', self.callback, 10)
        self.pub = self.create_publisher(
            Image, '/trackhist_compressed', 5)

        self.get_logger().info(
            f'trackhist compressor started: '
            f'{self.target_width}x{self.target_height} @ ~3Hz')

    def callback(self, msg):
        now = self.get_clock().now().nanoseconds / 1e9
        if now - self.last_publish < self.publish_interval:
            return
        self.last_publish = now

        try:
            cv_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().warn(f'cv_bridge error: {e}')
            return

        # Downsample
        small = cv2.resize(cv_img, (self.target_width, self.target_height),
                           interpolation=cv2.INTER_AREA)

        # Convert back and publish
        out_msg = self.bridge.cv2_to_imgmsg(small, encoding='bgr8')
        out_msg.header = msg.header
        self.pub.publish(out_msg)


def main(args=None):
    rclpy.init(args=args)
    node = TrackhistCompressor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
