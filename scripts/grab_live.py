#!/usr/bin/env python3
import rclpy, cv2
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import numpy as np, time
rclpy.init()
node = rclpy.create_node('grab_live')
holder = []
node.create_subscription(Image, '/camera/camera/infra1/image_rect_raw', lambda m: holder.append(m), 10)
br = CvBridge()
t0 = time.time()
while time.time() - t0 < 10 and len(holder) < 2:
    rclpy.spin_once(node, timeout_sec=0.3)
if holder:
    img = br.imgmsg_to_cv2(holder[-1], 'mono8')
    cv2.imwrite('/tmp/live_frame.png', img)
    print('saved %dx%d min=%d max=%d mean=%.1f std=%.1f' % (img.shape[1], img.shape[0], img.min(), img.max(), img.mean(), img.std()))
else:
    print('NO FRAMES')
node.destroy_node()
rclpy.shutdown()
