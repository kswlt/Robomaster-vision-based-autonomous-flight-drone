#!/usr/bin/env python3
"""Ground-test bridge: ROS stereo pose + PX4 USB MAVLink.

This sends position-only VISION_POSITION_ESTIMATE messages. It never arms,
changes mode, or sends actuator commands. Sending is automatically suppressed
when PX4 reports the armed flag.
"""
import math
import threading
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Int32


class VisionMavlinkBridge(Node):
    def __init__(self, mav):
        super().__init__("vision_mavlink_bridge")
        self.mav = mav
        self.lock = threading.Lock()
        self.armed = False
        self.tracking_ok = False
        self.sent = 0
        self.imu_pub = self.create_publisher(Imu, "/imu/data", 50)
        self.create_subscription(PoseStamped, "/orb_slam3/stereo/pose", self.pose_cb, 10)
        self.create_subscription(Int32, "/orb_slam3/stereo/tracking_state", self.state_cb, 10)
        self.create_timer(5.0, self.report)
        self.get_logger().info("USB vision bridge ready; position-only output, armed-send guard enabled")

    def report(self):
        with self.lock:
            armed, tracking_ok = self.armed, self.tracking_ok
        self.get_logger().info(
            f"vision_sent={self.sent} tracking_ok={tracking_ok} px4_armed={armed}")

    def state_cb(self, msg):
        with self.lock:
            self.tracking_ok = msg.data == 2

    def pose_cb(self, msg):
        with self.lock:
            armed = self.armed
            tracking_ok = self.tracking_ok
        if armed or not tracking_ok:
            return
        # ORB-SLAM3 camera convention (x right, y down, z forward) to PX4 NED
        # for a forward-facing, level-mounted camera. Verify on the ground first.
        p = msg.pose.position
        north, east, down = p.z, p.x, p.y
        usec = int(msg.header.stamp.sec * 1_000_000 + msg.header.stamp.nanosec / 1000)
        try:
            self.mav.mav.vision_position_estimate_send(
                usec, north, east, down, math.nan, math.nan, math.nan)
            self.sent += 1
        except Exception as exc:
            self.get_logger().error("MAVLink vision send failed: %s", exc)

    def publish_imu(self, msg):
        imu = Imu()
        imu.header.stamp = self.get_clock().now().to_msg()
        imu.header.frame_id = "fc_imu"
        imu.orientation_covariance[0] = -1.0
        imu.angular_velocity.x = msg.xgyro
        imu.angular_velocity.y = msg.ygyro
        imu.angular_velocity.z = msg.zgyro
        imu.linear_acceleration.x = msg.xacc
        imu.linear_acceleration.y = msg.yacc
        imu.linear_acceleration.z = msg.zacc
        self.imu_pub.publish(imu)


def main():
    from pymavlink import mavutil

    mav = mavutil.mavlink_connection("/dev/ttyACM0", baud=115200, timeout=2)
    mav.wait_heartbeat(timeout=10)
    node_holder = {}

    rclpy.init()
    node = VisionMavlinkBridge(mav)
    node_holder["node"] = node

    def reader():
        while rclpy.ok():
            message = mav.recv_match(blocking=True, timeout=0.5)
            if message is None:
                continue
            kind = message.get_type()
            if kind == "HEARTBEAT":
                armed = bool(message.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                with node.lock:
                    node.armed = armed
                continue
            if kind == "HIGHRES_IMU":
                node.publish_imu(message)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
