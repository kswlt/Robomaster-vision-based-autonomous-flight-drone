#!/usr/bin/env python3
"""Print compact live statistics for OpenVINS odometry and path topics."""

import math
import time

import rclpy
from nav_msgs.msg import Odometry, Path
from rclpy.node import Node


class Inspector(Node):
    def __init__(self):
        super().__init__("vio_topic_inspector")
        self.got_path = False
        self.got_odom = False
        self.create_subscription(Path, "/pathimu", self.path_callback, 1)
        self.create_subscription(Odometry, "/odomimu", self.odom_callback, 1)

    def path_callback(self, msg):
        if self.got_path:
            return
        if not msg.poses:
            print("PATH poses=0", flush=True)
            self.got_path = True
            return
        xyz = [
            (pose.pose.position.x, pose.pose.position.y, pose.pose.position.z)
            for pose in msg.poses
        ]
        first = xyz[0]
        last = xyz[-1]
        mins = tuple(min(point[i] for point in xyz) for i in range(3))
        maxs = tuple(max(point[i] for point in xyz) for i in range(3))
        displacement = math.dist(first, last)
        print(
            f"PATH poses={len(xyz)} first={first} last={last} "
            f"displacement={displacement:.4f} "
            f"bounds_x=({mins[0]:.4f},{maxs[0]:.4f}) "
            f"bounds_y=({mins[1]:.4f},{maxs[1]:.4f}) "
            f"bounds_z=({mins[2]:.4f},{maxs[2]:.4f})",
            flush=True,
        )
        self.got_path = True

    def odom_callback(self, msg):
        if self.got_odom:
            return
        pos = msg.pose.pose.position
        vel = msg.twist.twist.linear
        speed = math.sqrt(vel.x**2 + vel.y**2 + vel.z**2)
        variance = max(
            msg.pose.covariance[0],
            msg.pose.covariance[7],
            msg.pose.covariance[14],
        )
        print(
            f"ODOM position=({pos.x:.4f},{pos.y:.4f},{pos.z:.4f}) "
            f"velocity=({vel.x:.4f},{vel.y:.4f},{vel.z:.4f}) "
            f"speed={speed:.4f} max_position_variance={variance:.6f}",
            flush=True,
        )
        self.got_odom = True


def main():
    rclpy.init()
    node = Inspector()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and not (node.got_path and node.got_odom):
        rclpy.spin_once(node, timeout_sec=0.5)
    node.destroy_node()
    rclpy.shutdown()
    if not (node.got_path and node.got_odom):
        raise SystemExit("Timed out waiting for /pathimu and /odomimu")


if __name__ == "__main__":
    main()
