#!/usr/bin/env python3
import rclpy, time
from rclpy.qos import QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry

rclpy.init()
node = rclpy.create_node('odom_throttle')
pub = node.create_publisher(Odometry, '/odomimu_viz', 10)
qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
last_pub = 0.0
RATE = 30.0

def cb(m):
    global last_pub
    now = time.time()
    if now - last_pub < 1.0 / RATE:
        return
    last_pub = now
    pub.publish(m)

node.create_subscription(Odometry, '/odomimu', cb, qos)
print('odom_throttle ready: /odomimu -> /odomimu_viz @%dHz' % RATE, flush=True)
rclpy.spin(node)
