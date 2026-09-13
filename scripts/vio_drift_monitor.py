#!/usr/bin/env python3
"""
VIO drift monitor.
Records initial position on startup, publishes drift distance and components.

Topics:
  /vio/drift_distance  (std_msgs/Float32)  - Euclidean distance from init point (m)
  /vio/drift_xy        (std_msgs/Float32)  - Horizontal drift (m)
  /vio/drift_z         (std_msgs/Float32)  - Vertical drift (m)
  /vio/velocity_norm   (std_msgs/Float32)  - Current speed (m/s)
"""

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from std_msgs.msg import Float32
import math


class VIODriftMonitor(Node):
    def __init__(self):
        super().__init__('vio_drift_monitor')
        self.init_pos = None
        self.init_set = False

        self.drift_pub = self.create_publisher(Float32, '/vio/drift_distance', 10)
        self.drift_xy_pub = self.create_publisher(Float32, '/vio/drift_xy', 10)
        self.drift_z_pub = self.create_publisher(Float32, '/vio/drift_z', 10)
        self.vel_pub = self.create_publisher(Float32, '/vio/velocity_norm', 10)

        self.sub = self.create_subscription(
            Odometry, '/odomimu', self.odom_callback, 10)

        self.get_logger().info('VIO drift monitor started (set initial pos on first odom)')

    def odom_callback(self, msg):
        p = msg.pose.pose.position
        v = msg.twist.twist.linear

        if not self.init_set:
            self.init_pos = (p.x, p.y, p.z)
            self.init_set = True
            self.get_logger().info(
                f'Initial position set: x={p.x:.3f} y={p.y:.3f} z={p.z:.3f}')

        dx = p.x - self.init_pos[0]
        dy = p.y - self.init_pos[1]
        dz = p.z - self.init_pos[2]

        drift_3d = math.sqrt(dx*dx + dy*dy + dz*dz)
        drift_xy = math.sqrt(dx*dx + dy*dy)
        vel_norm = math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z)

        m = Float32()
        m.data = drift_3d
        self.drift_pub.publish(m)

        m2 = Float32()
        m2.data = drift_xy
        self.drift_xy_pub.publish(m2)

        m3 = Float32()
        m3.data = dz
        self.drift_z_pub.publish(m3)

        m4 = Float32()
        m4.data = vel_norm
        self.vel_pub.publish(m4)


def main(args=None):
    rclpy.init(args=args)
    node = VIODriftMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
