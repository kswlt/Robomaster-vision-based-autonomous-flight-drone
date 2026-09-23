#!/usr/bin/env python3
import rclpy, time
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import PoseStamped

rclpy.init()
node = rclpy.create_node('odom_to_path')
pub = node.create_publisher(Path, '/trajectory', 10)
qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                 history=HistoryPolicy.KEEP_LAST, durability=DurabilityPolicy.VOLATILE)
path = Path()
last_sample = 0.0
last_pub = 0.0
MAX = 2000          # ~40s of trajectory at 20ms sampling
PUB_INT = 0.1       # publish at 10 Hz

def cb(m):
    global last_sample, last_pub
    t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    now = time.time()
    if t - last_sample < 0.02:
        return
    last_sample = t
    ps = PoseStamped()
    ps.header = m.header
    ps.pose = m.pose.pose
    path.header = m.header
    path.poses.append(ps)
    if len(path.poses) > MAX:
        path.poses = path.poses[-MAX:]
    if now - last_pub >= PUB_INT:
        last_pub = now
        pub.publish(path)

node.create_subscription(Odometry, '/odomimu', cb, qos)
print('odom_to_path ready: /odomimu -> /trajectory @10Hz max=%d pts' % MAX, flush=True)
rclpy.spin(node)
