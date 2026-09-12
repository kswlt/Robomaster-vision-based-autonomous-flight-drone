#!/usr/bin/env python3
"""
合并的VIO桥接节点：
1. 从PX4飞控读取IMU数据，发布为ROS2 sensor_msgs/Imu
2. 订阅VIO里程计，发送VISION_POSITION_ESTIMATE和ODOMETRY给飞控
只使用一个串口连接，避免冲突
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from nav_msgs.msg import Odometry
from pymavlink import mavutil
from pymavlink.dialects.v20 import common as mavlink_v20
import time
import threading

class VIOBridge(Node):
    def __init__(self):
        super().__init__('vio_bridge')

        # 参数
        self.declare_parameter('serial_port', '/dev/ttyACM0')
        self.declare_parameter('baudrate', 921600)
        self.declare_parameter('imu_topic', '/imu')
        self.declare_parameter('odom_topic', '/odomimu')

        port = self.get_parameter('serial_port').value
        baud = self.get_parameter('baudrate').value
        imu_topic = self.get_parameter('imu_topic').value
        odom_topic = self.get_parameter('odom_topic').value

        # IMU发布者
        self.imu_pub = self.create_publisher(Imu, imu_topic, 10)

        # VIO里程计订阅者
        self.odom_sub = self.create_subscription(
            Odometry, odom_topic, self.odom_callback, 10)

        self.last_send = 0.0
        self.last_est_print = 0.0
        self.running = True

        # 连接飞控
        self.get_logger().info(f'连接PX4: {port} @ {baud}')
        self.master = None
        try:
            self.master = mavutil.mavlink_connection(port, baud=baud)
            # 设置源系统/组件ID（compid=0会被PX4丢弃）
            self.master.srcSystem = 42       # 机载电脑系统ID
            self.master.srcComponent = 191   # MAV_COMP_ID_ONBOARD_COMPUTER
            self.get_logger().info('等待飞控心跳...')
            heartbeat = self.master.wait_heartbeat(timeout=15)
            if heartbeat:
                self.get_logger().info(f'PX4连接成功, 系统ID: {self.master.target_system}')
            else:
                self.get_logger().error('等待心跳超时，请检查飞控连接')
                self.master = None
                return

            # 请求IMU数据流
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS,
                200, 1)

            # 用MAV_CMD_SET_MESSAGE_INTERVAL强制设置HIGHRES_IMU 200Hz
            # HIGHRES_IMU消息ID=234, 200Hz=间隔5000微秒
            try:
                self.master.mav.command_long_send(
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                    0,
                    234,      # MAVLINK_MSG_ID_HIGHRES_IMU
                    5000,     # 200Hz (5000us)
                    0, 0, 0, 0, 0)
                self.get_logger().info('已强制请求200Hz IMU (SET_MESSAGE_INTERVAL)')
            except Exception as e:
                self.get_logger().warn(f'SET_MESSAGE_INTERVAL失败: {e}')
            self.get_logger().info('已请求200Hz IMU数据流')

            # 请求EKF状态流（用于确认视觉融合）
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
                10, 1)
            self.get_logger().info('已请求EKF状态流')

        except Exception as e:
            self.get_logger().error(f'连接PX4失败: {e}')
            import traceback
            traceback.print_exc()
            self.master = None
            return

        # 启动IMU读取线程
        if self.master is not None:
            self.imu_thread = threading.Thread(target=self.read_imu_loop, daemon=True)
            self.imu_thread.start()
            self.get_logger().info('IMU读取线程已启动')

    def read_imu_loop(self):
        """从飞控读取IMU数据并发布，同时监听EKF融合状态"""
        while self.running:
            try:
                msg = self.master.recv_match(
                    type=['HIGHRES_IMU', 'ESTIMATOR_STATUS'],
                    blocking=True, timeout=1.0)
                if msg is None:
                    continue

                msg_type = msg.get_type()

                # EKF状态消息：确认视觉融合
                if msg_type == 'ESTIMATOR_STATUS':
                    now_t = time.time()
                    if now_t - self.last_est_print > 2.0:
                        self.last_est_print = now_t
                        flags = msg.flags
                        vis_pos_horiz = bool(flags & 16)   # ESTIMATOR_POS_HORIZ_REL
                        vis_vel_horiz = bool(flags & 4)    # ESTIMATOR_VELOCITY_HORIZ
                        self.get_logger().info(
                            f'EKF状态: 视觉水平位置={vis_pos_horiz} '
                            f'视觉水平速度={vis_vel_horiz} flags={flags} '
                            f'posH={msg.pos_horiz_ratio:.3f} '
                            f'posV={msg.pos_vert_ratio:.3f} '
                            f'vel={getattr(msg, "vel_ratio", "NA")}')
                    continue

                imu_msg = Imu()
                imu_msg.header.stamp = self.get_clock().now().to_msg()
                imu_msg.header.frame_id = 'imu'

                # PX4 NED -> ROS ENU 转换
                # 角速度: NED(roll,pitch,yaw) -> ENU
                imu_msg.angular_velocity.x = msg.xgyro
                imu_msg.angular_velocity.y = -msg.ygyro
                imu_msg.angular_velocity.z = -msg.zgyro

                # 加速度: NED -> ENU
                imu_msg.linear_acceleration.x = msg.xacc
                imu_msg.linear_acceleration.y = -msg.yacc
                imu_msg.linear_acceleration.z = -msg.zacc

                # 方向四元数（暂时不提供，由VIO估计）
                imu_msg.orientation.x = 0.0
                imu_msg.orientation.y = 0.0
                imu_msg.orientation.z = 0.0
                imu_msg.orientation.w = 1.0

                self.imu_pub.publish(imu_msg)

            except Exception as e:
                self.get_logger().warn(f'IMU读取错误: {e}')
                time.sleep(0.1)

    def odom_callback(self, msg):
        """收到VIO里程计，发送给飞控"""
        if self.master is None:
            return

        now = time.time()
        if now - self.last_send < 0.03:  # 限频30Hz
            return
        self.last_send = now
        # ROS ENU -> PX4 NED 坐标系转换
        x_ned = msg.pose.pose.position.y
        y_ned = msg.pose.pose.position.x
        z_ned = -msg.pose.pose.position.z

        # 四元数 ENU -> NED：q_ned = q_en2ned ⊗ q_enu
        # q_en2ned = [0, 0.7071, 0.7071, 0]（绕xy平面45°轴转180°：x→y, y→x, z→-z）
        qw_e, qx_e, qy_e, qz_e = (msg.pose.pose.orientation.w,
                                  msg.pose.pose.orientation.x,
                                  msg.pose.pose.orientation.y,
                                  msg.pose.pose.orientation.z)
        # 四元数乘法 q1 ⊗ q2
        def quat_mult(q1, q2):
            w1, x1, y1, z1 = q1
            w2, x2, y2, z2 = q2
            return (w1*w2 - x1*x2 - y1*y2 - z1*z2,
                    w1*x2 + x1*w2 + y1*z2 - z1*y2,
                    w1*y2 - x1*z2 + y1*w2 + z1*x2,
                    w1*z2 + x1*y2 - y1*x2 + z1*w2)
        qw_ned, qx_ned, qy_ned, qz_ned = quat_mult(
            (0.0, 0.7071067811865476, 0.7071067811865476, 0.0),
            (qw_e, qx_e, qy_e, qz_e))

        # 速度 NED
        vx_ned = msg.twist.twist.linear.y
        vy_ned = msg.twist.twist.linear.x
        vz_ned = -msg.twist.twist.linear.z

        # 发送VISION_POSITION_ESTIMATE（带covariance和真实姿态，9字段MAVLink2定义）
        try:
            import math
            # 四元数(NED)转欧拉角
            w, x, y, z = qw_ned, qx_ned, qy_ned, qz_ned
            roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
            sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
            pitch = math.asin(sinp)
            yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

            # covariance: 6x6位姿协方差上三角（行主序）
            # cov[0]=X方差, cov[6]=Y方差, cov[11]=Z方差
            # cov[3]=roll方差, cov[7]=pitch方差, cov[12]=yaw方差
            cov = [0.0] * 21
            cov[0] = 0.01   # X position variance (0.1m)
            cov[6] = 0.01   # Y position variance
            cov[11] = 0.01  # Z position variance
            cov[3] = 0.01   # roll variance (0.1rad)
            cov[7] = 0.01   # pitch variance
            cov[12] = 0.01  # yaw variance

            # 用v20.common方言（9字段定义，含covariance）
            # 不能再用master.mav（7字段旧版），直接构造v20消息
            v20_mav = mavlink_v20.MAVLink(None, srcSystem=42, srcComponent=191)
            msg_out = mavlink_v20.MAVLink_vision_position_estimate_message(
                int(now * 1e6),
                x_ned, y_ned, z_ned,
                roll, pitch, yaw,   # 真实姿态
                cov, 0)             # covariance, reset_counter
            buf = msg_out.pack(v20_mav)
            self.master.port.write(buf)
            self.send_count = getattr(self, 'send_count', 0) + 1
            if self.send_count % 50 == 0:
                self.get_logger().info(
                    f'已发送VISION_POSITION_ESTIMATE(姿态+协方差): '
                    f'第{self.send_count}条, {len(buf)}字节, '
                    f'x={x_ned:.2f} y={y_ned:.2f} z={z_ned:.2f} '
                    f'r={math.degrees(roll):.1f} p={math.degrees(pitch):.1f} y={math.degrees(yaw):.1f}')
        except Exception as e:
            self.get_logger().warn(f'VISION_POSITION send failed: {e}')

#         # 发送ODOMETRY消息
#         try:
#             self.master.mav.odometry_send(
#                 int(now * 1e6),
#                 mavutil.mavlink.MAV_FRAME_LOCAL_FRD,
#                 mavutil.mavlink.MAV_FRAME_BODY_FRD,
#                 x_ned, y_ned, z_ned,
#                 [qw_ned, qx_ned, qy_ned, qz_ned],
#                 vx_ned, vy_ned, vz_ned,
#                 0.0, 0.0, 0.0,
#                 [0.0]*21,
#                 [0.0]*21,
#                 0, 2, 0, 0
#             )
#         except Exception as e:
#             self.get_logger().warn(f'ODOMETRY send failed: {e}')
# 
    def destroy_node(self):
        self.running = False
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = VIOBridge()
    if node.master is not None:
        rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
