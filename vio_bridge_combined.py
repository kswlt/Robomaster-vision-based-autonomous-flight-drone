#!/usr/bin/env python3
"""
合并的VIO桥接节点：
1. 从PX4飞控读取IMU数据，发布为ROS2 sensor_msgs/Imu
2. 订阅VIO里程计，发送VISION_POSITION_ESTIMATE和ODOMETRY给飞控
只使用一个串口连接，避免冲突
"""
import glob
import math
import os
import threading
import time

import rclpy
from nav_msgs.msg import Odometry
from pymavlink import mavutil
from pymavlink.dialects.v20 import common as mavlink_v20
from rclpy.node import Node
from sensor_msgs.msg import Imu

class VIOBridge(Node):
    SYSTEM_ID = 42
    COMPONENT_ID = 197  # MAV_COMP_ID_VISUAL_INERTIAL_ODOMETRY
    EXTERNAL_ATTITUDE_CMD = 620

    def __init__(self):
        super().__init__('vio_bridge')

        # 参数
        self.declare_parameter('serial_port', '/dev/ttyACM0')
        self.declare_parameter('baudrate', 921600)
        self.declare_parameter('imu_topic', '/imu')
        self.declare_parameter('odom_topic', '/odomimu')
        # Fail-safe default: the estimator can be observed without injecting
        # anything into PX4.  Enable explicitly only after a controlled test.
        self.declare_parameter('send_vision_to_px4', False)

        port = self.get_parameter('serial_port').value
        baud = self.get_parameter('baudrate').value
        imu_topic = self.get_parameter('imu_topic').value
        odom_topic = self.get_parameter('odom_topic').value
        self.send_vision_to_px4 = bool(
            self.get_parameter('send_vision_to_px4').value)
        # 自动检测串口：USB重枚举后ttyACM编号可能变化(ttyACM0→ttyACM1)
        if not os.path.exists(port):
            candidates = sorted(glob.glob('/dev/ttyACM*'))
            if candidates:
                self.get_logger().info(f'串口{port}不存在, 自动选择: {candidates[0]}')
                port = candidates[0]
            else:
                self.get_logger().error(f'未找到任何/dev/ttyACM*串口, 请检查飞控USB连接')
        # 保存供reconnect使用
        self.serial_port = port
        self.baudrate = baud

        # IMU发布者
        self.imu_pub = self.create_publisher(Imu, imu_topic, 10)

        # VIO里程计订阅者
        self.odom_sub = self.create_subscription(
            Odometry, odom_topic, self.odom_callback, 10)

        self.last_send = 0.0
        self.last_est_print = 0.0
        self.last_pos_print = 0.0
        self.running = True
        self.master_lock = threading.RLock()
        self.reset_counter = int(time.time()) & 0xFF

        # Preserve the PX4 sampling interval while mapping its boot clock to ROS time.
        # Arrival-time stamping adds serial and scheduler jitter to every IMU sample.
        self.imu_clock_offset = None
        self.last_imu_sensor_time = None
        self.last_imu_stamp = None
        self.last_clock_refine_log = 0.0

        # VIO健康门控：启动时先观察，运行后 fail-closed 并锁存故障。
        self.vio_healthy = False
        self.vio_started_sending = False
        self.fatal_latched = False
        self.healthy_count = 0
        self.bad_count = 0
        self.first_odom_time = None
        self.last_odom_time = None
        self.last_observed_pos = None
        self.health_log_ts = 0.0
        self.HEALTHY_COUNT = 90
        self.BAD_COUNT = 30
        self.STARTUP_TIMEOUT = 20.0
        self.STARTUP_POSITION_LIMIT = 0.5
        self.STARTUP_SPEED_LIMIT = 0.2
        self.STARTUP_VARIANCE_LIMIT = 0.1
        self.ABSOLUTE_LIMIT = 1000.0
        self.MAX_POSITION_VARIANCE = 20.0  # 2 m one-sigma
        self.MAX_POSITION_RATE = 50.0
        self.MAX_RATE_DISAGREEMENT = 3.0
        self.output_log_ts = 0.0

        mode = '启用（会写入PX4）' if self.send_vision_to_px4 else '关闭（仅观察，不写入PX4）'
        self.get_logger().warn(f'PX4视觉输出: {mode}')

        # Heading reset is only considered successful after COMMAND_ACK.
        self.yaw_reset_sent = False
        self.yaw_reset_pending = False
        self.yaw_reset_attempts = 0
        self.last_yaw_attempt = 0.0
        self.YAW_RETRY_INTERVAL = 2.0
        self.YAW_MAX_ATTEMPTS = 5

        # 连接飞控
        self.get_logger().info(f'连接PX4: {port} @ {baud}')
        self.master = None
        self.read_error_count = 0

        # 重试连接（pymavlink偶发解析崩溃TypeError，必须自动重连）
        for attempt in range(10):
            try:
                self.master = mavutil.mavlink_connection(port, baud=baud)
                # 设置源系统/组件ID（compid=0会被PX4丢弃）
                self.master.srcSystem = self.SYSTEM_ID
                self.master.srcComponent = self.COMPONENT_ID
                self.get_logger().info(f'等待飞控心跳... (第{attempt+1}次尝试)')
                heartbeat = self.master.wait_heartbeat(timeout=15)
                if heartbeat:
                    self.get_logger().info(f'PX4连接成功, 系统ID: {self.master.target_system}')
                    break
                self.get_logger().error('等待心跳超时，重试连接...')
            except Exception as e:
                self.get_logger().error(f'连接异常({e})，2秒后重连...')
                try:
                    self.master.close()
                except Exception:
                    pass
                self.master = None
                time.sleep(2)
        else:
            self.get_logger().error('多次连接失败，桥接退出')
            return

        try:
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

            # 请求本地位置流（验证位置跟随）
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_POSITION,
                5, 1)
            self.get_logger().info('已请求本地位置流')

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

    def imu_timestamp(self, msg):
        """Map PX4 HIGHRES_IMU sample time into the ROS system-time domain."""
        now = self.get_clock().now().nanoseconds * 1e-9
        sensor_usec = int(getattr(msg, 'time_usec', 0) or 0)
        if sensor_usec <= 0:
            stamp = now
        else:
            sensor_time = sensor_usec * 1e-6
            if sensor_usec >= 1_000_000_000_000:
                stamp = sensor_time
            else:
                clock_reset = (
                    self.last_imu_sensor_time is not None and
                    sensor_time < self.last_imu_sensor_time - 0.5)
                arrival_offset = now - sensor_time
                if self.imu_clock_offset is None or clock_reset:
                    self.imu_clock_offset = arrival_offset
                    self.get_logger().info(
                        f'PX4 IMU时钟已映射到ROS时间, offset={self.imu_clock_offset:.6f}s')
                elif arrival_offset < self.imu_clock_offset:
                    # Serial delivery latency is non-negative and varies with
                    # queueing.  Anchoring to the first packet made the whole
                    # IMU clock late by up to ~12 ms in measured runs.  The
                    # lowest observed arrival offset is the best available
                    # one-way clock estimate when PX4 sends no SYSTEM_TIME.
                    correction = self.imu_clock_offset - arrival_offset
                    self.imu_clock_offset = arrival_offset
                    if correction > 0.001 and now - self.last_clock_refine_log > 1.0:
                        self.last_clock_refine_log = now
                        self.get_logger().info(
                            f'PX4 IMU时钟下包络校正: -{correction * 1e3:.2f}ms, '
                            f'offset={self.imu_clock_offset:.6f}s')
                stamp = sensor_time + self.imu_clock_offset
                self.last_imu_sensor_time = sensor_time

        # PX4 can change the HIGHRES_IMU time base after boot/time-sync.  A
        # fixed offset would then put IMU samples minutes into the future and
        # OpenVINS would reject every image as out-of-order.  Re-anchor only
        # after a large discontinuity; normal samples still retain PX4 timing.
        if abs(stamp - now) > 0.5:
            self.get_logger().warn(
                f'PX4 IMU时基跳变({stamp - now:+.3f}s)，重新对齐ROS时间')
            if 0 < sensor_usec < 1_000_000_000_000:
                self.imu_clock_offset = now - sensor_time
            stamp = now
            self.last_imu_stamp = None

        # Guard against duplicate/backward timestamps after a serial reconnect.
        if self.last_imu_stamp is not None and stamp <= self.last_imu_stamp:
            stamp = self.last_imu_stamp + 1e-6
        self.last_imu_stamp = stamp
        sec = int(stamp)
        nanosec = int((stamp - sec) * 1e9)
        return sec, nanosec

    def handle_command_ack(self, msg):
        if int(getattr(msg, 'command', -1)) != self.EXTERNAL_ATTITUDE_CMD:
            return
        result = int(getattr(msg, 'result', -1))
        accepted = getattr(mavutil.mavlink, 'MAV_RESULT_ACCEPTED', 0)
        in_progress = getattr(mavutil.mavlink, 'MAV_RESULT_IN_PROGRESS', 5)
        if result == accepted:
            self.yaw_reset_sent = True
            self.yaw_reset_pending = False
            self.get_logger().info('外部航向初始化已由PX4确认(COMMAND_ACK=ACCEPTED)')
        elif result == in_progress:
            self.get_logger().info('外部航向初始化处理中(COMMAND_ACK=IN_PROGRESS)')
        else:
            self.yaw_reset_pending = False
            self.get_logger().error(f'外部航向初始化被PX4拒绝, COMMAND_ACK result={result}')

    def latch_vio_fatal(self, reason):
        if self.fatal_latched:
            return
        self.fatal_latched = True
        self.vio_healthy = False
        self.get_logger().error(
            f'VIO_FATAL: {reason}; 已停止视觉输出，故障将锁存并等待人工复位')

    def maybe_send_heading_reset(self, yaw, now):
        if self.yaw_reset_sent or self.fatal_latched:
            return
        if now - self.last_yaw_attempt < self.YAW_RETRY_INTERVAL:
            return
        if self.yaw_reset_attempts >= self.YAW_MAX_ATTEMPTS:
            self.latch_vio_fatal('外部航向初始化连续5次未得到PX4确认')
            return

        self.yaw_reset_pending = True
        self.yaw_reset_attempts += 1
        self.last_yaw_attempt = now
        yaw_deg = math.degrees(yaw)
        try:
            with self.master_lock:
                self.master.mav.command_long_send(
                    self.master.target_system,
                    self.master.target_component,
                    self.EXTERNAL_ATTITUDE_CMD,
                    0,
                    float('nan'), float('nan'), float(yaw_deg),
                    0.0, 0.0, 0.0, 20.0)
            self.get_logger().info(
                f'已请求外部航向初始化: {yaw_deg:.1f}度 '
                f'(command={self.EXTERNAL_ATTITUDE_CMD}, attempt={self.yaw_reset_attempts})')
        except Exception as exc:
            self.yaw_reset_pending = False
            self.get_logger().warn(f'外部航向初始化发送失败: {exc}')

    def reconnect(self):
        """串口异常时自动重连飞控（pymavlink偶发解析崩溃）"""
        with self.master_lock:
            try:
                if self.master is not None:
                    self.master.close()
            except Exception:
                pass
            self.master = None
        for attempt in range(5):
            try:
                with self.master_lock:
                    self.master = mavutil.mavlink_connection(self.serial_port, baud=self.baudrate)
                    self.master.srcSystem = self.SYSTEM_ID
                    self.master.srcComponent = self.COMPONENT_ID
                self.get_logger().info(f'重连等待心跳... (第{attempt+1}次)')
                hb = self.master.wait_heartbeat(timeout=10)
                if hb:
                    self.get_logger().info('重连成功, 重新请求数据流')
                    try:
                        self.master.mav.command_long_send(
                            self.master.target_system, self.master.target_component,
                            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                            234, 5000, 0, 0, 0, 0, 0)
                        self.master.mav.request_data_stream_send(
                            self.master.target_system, self.master.target_component,
                            mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 10, 1)
                        self.master.mav.request_data_stream_send(
                            self.master.target_system, self.master.target_component,
                            mavutil.mavlink.MAV_DATA_STREAM_POSITION, 5, 1)
                    except Exception as e:
                        self.get_logger().warn(f'重连后请求流失败: {e}')
                    self.imu_clock_offset = None
                    self.last_imu_sensor_time = None
                    self.last_imu_stamp = None
                    self.yaw_reset_sent = False
                    self.yaw_reset_pending = False
                    self.yaw_reset_attempts = 0
                    return True
            except Exception as e:
                self.get_logger().error(f'重连异常({e})...')
                try:
                    self.master.close()
                except Exception:
                    pass
                self.master = None
                time.sleep(2)
        self.get_logger().error('重连多次失败')
        return False

    def read_imu_loop(self):
        """从飞控读取IMU数据并发布，同时监听EKF融合状态"""
        while self.running:
            try:
                msg = self.master.recv_match(
                    type=['HIGHRES_IMU', 'ESTIMATOR_STATUS', 'LOCAL_POSITION_NED', 'COMMAND_ACK'],
                    blocking=True, timeout=1.0)
                if msg is None:
                    continue

                self.read_error_count = 0
                msg_type = msg.get_type()

                if msg_type == 'COMMAND_ACK':
                    self.handle_command_ack(msg)
                    continue

                # 本地位置：验证EKF位置是否跟随VIO
                if msg_type == 'LOCAL_POSITION_NED':
                    now_t = time.time()
                    if now_t - self.last_pos_print > 1.0:
                        self.last_pos_print = now_t
                        self.get_logger().info(
                            f'EKF位置: x={msg.x:.2f} y={msg.y:.2f} z={msg.z:.2f} '
                            f'vx={msg.vx:.2f} vy={msg.vy:.2f} vz={msg.vz:.2f}')
                    continue

                # EKF状态消息：确认视觉融合
                if msg_type == 'ESTIMATOR_STATUS':
                    now_t = time.time()
                    if now_t - self.last_est_print > 2.0:
                        self.last_est_print = now_t
                        flags = msg.flags
                        pos_horiz_rel = bool(flags & 8)
                        vel_horiz = bool(flags & 2)
                        self.get_logger().info(
                            f'EKF状态: 水平相对位置有效={pos_horiz_rel} 水平速度有效={vel_horiz} '
                            f'flags={flags} '
                            f'posH={msg.pos_horiz_ratio:.3f} '
                            f'posV={msg.pos_vert_ratio:.3f} '
                            f'vel={getattr(msg, "vel_ratio", "NA")}')
                    continue

                imu_msg = Imu()
                stamp_sec, stamp_nanosec = self.imu_timestamp(msg)
                imu_msg.header.stamp.sec = stamp_sec
                imu_msg.header.stamp.nanosec = stamp_nanosec
                imu_msg.header.frame_id = 'imu'

                # PX4 body FRD -> ROS body FLU
                imu_msg.angular_velocity.x = msg.xgyro
                imu_msg.angular_velocity.y = -msg.ygyro
                imu_msg.angular_velocity.z = -msg.zgyro

                imu_msg.linear_acceleration.x = msg.xacc
                imu_msg.linear_acceleration.y = -msg.yacc
                imu_msg.linear_acceleration.z = -msg.zacc

                # HIGHRES_IMU does not contain orientation.
                imu_msg.orientation.x = 0.0
                imu_msg.orientation.y = 0.0
                imu_msg.orientation.z = 0.0
                imu_msg.orientation.w = 1.0
                imu_msg.orientation_covariance[0] = -1.0

                self.imu_pub.publish(imu_msg)

            except Exception as e:
                self.get_logger().warn(f'IMU读取错误: {e}')
                self.read_error_count += 1
                if self.read_error_count >= 15:
                    self.get_logger().error('串口连续异常，尝试自动重连...')
                    if self.reconnect():
                        self.read_error_count = 0
                        self.get_logger().info('重连完成，恢复读取')
                    else:
                        self.get_logger().error('自动重连失败，持续重试中...')
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

        # ============ VIO健康门控（防发散数据污染EKF） ============
        # 四元数(NED)转欧拉角
        w, x, y, z = qw_ned, qx_ned, qy_ned, qz_ned
        roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
        sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
        pitch = math.asin(sinp)
        yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

        observed_speed = 0.0
        current_pos = (x_ned, y_ned, z_ned)
        if self.first_odom_time is None:
            self.first_odom_time = now
        if self.last_odom_time is not None and self.last_observed_pos is not None:
            dt = now - self.last_odom_time
            if dt > 1e-4:
                dx = x_ned - self.last_observed_pos[0]
                dy = y_ned - self.last_observed_pos[1]
                dz = z_ned - self.last_observed_pos[2]
                observed_speed = math.sqrt(dx*dx + dy*dy + dz*dz) / dt
        self.last_odom_time = now
        self.last_observed_pos = current_pos

        abs_pos = math.sqrt(x_ned*x_ned + y_ned*y_ned + z_ned*z_ned)
        reported_speed = math.sqrt(vx_ned*vx_ned + vy_ned*vy_ned + vz_ned*vz_ned)
        pose_cov = msg.pose.covariance
        position_variances = (pose_cov[0], pose_cov[7], pose_cov[14])
        max_position_variance = max(position_variances)
        quaternion_norm = math.sqrt(qw_e*qw_e + qx_e*qx_e + qy_e*qy_e + qz_e*qz_e)

        checked_values = (
            x_ned, y_ned, z_ned, roll, pitch, yaw,
            vx_ned, vy_ned, vz_ned, max_position_variance, quaternion_norm)
        bad_reasons = []
        if not all(math.isfinite(value) for value in checked_values):
            bad_reasons.append('位置/姿态/速度/协方差出现NaN或Inf')
        if abs(quaternion_norm - 1.0) > 0.05:
            bad_reasons.append(f'四元数模长异常({quaternion_norm:.3f})')
        if abs_pos > self.ABSOLUTE_LIMIT:
            bad_reasons.append(f'位置模长超限({abs_pos:.1f}m)')
        if max_position_variance < 0.0 or max_position_variance > self.MAX_POSITION_VARIANCE:
            bad_reasons.append(f'位置方差超限({max_position_variance:.3f}m^2)')
        if (observed_speed > self.MAX_POSITION_RATE and
                abs(observed_speed - reported_speed) > self.MAX_RATE_DISAGREEMENT):
            bad_reasons.append(
                f'位置跳变({observed_speed:.1f}m/s, VIO报告{reported_speed:.1f}m/s)')

        sample_good = not bad_reasons
        if not self.vio_started_sending:
            if abs_pos > self.STARTUP_POSITION_LIMIT:
                sample_good = False
                bad_reasons.append(f'启动位置不在原点附近({abs_pos:.1f}m)')
            if reported_speed > self.STARTUP_SPEED_LIMIT:
                sample_good = False
                bad_reasons.append(f'启动速度过高({reported_speed:.3f}m/s)')
            if max_position_variance > self.STARTUP_VARIANCE_LIMIT:
                sample_good = False
                bad_reasons.append(
                    f'启动位置方差过高({max_position_variance:.3f}m^2)')
            self.healthy_count = self.healthy_count + 1 if sample_good else 0
            if self.healthy_count >= self.HEALTHY_COUNT:
                self.vio_healthy = True
                self.vio_started_sending = True
                self.get_logger().info(
                    f'VIO健康门控通过: pos={abs_pos:.3f}m, speed={reported_speed:.3f}m/s, '
                    f'max_var={max_position_variance:.6f}m^2')
            elif now - self.first_odom_time > self.STARTUP_TIMEOUT:
                reason = ', '.join(bad_reasons) if bad_reasons else '启动健康样本不连续'
                self.latch_vio_fatal(f'启动健康检查超时: {reason}')
        elif self.vio_healthy:
            self.bad_count = 0 if sample_good else self.bad_count + 1
            if self.bad_count >= self.BAD_COUNT:
                self.latch_vio_fatal(', '.join(bad_reasons))

        if not self.vio_healthy:
            if not self.fatal_latched and now - self.health_log_ts > 2.0:
                self.health_log_ts = now
                self.get_logger().info(
                    f'等待VIO健康门控: {self.healthy_count}/{self.HEALTHY_COUNT}, '
                    f'pos={abs_pos:.3f}m, speed={reported_speed:.3f}m/s, '
                    f'max_var={max_position_variance:.6f}m^2')
            return

        # Keep consuming PX4 IMU and publishing ROS topics in diagnostic mode,
        # but do not reset heading or send any external-vision packet.
        if not self.send_vision_to_px4:
            if now - self.output_log_ts > 5.0:
                self.output_log_ts = now
                self.get_logger().info(
                    'VIO健康，但PX4视觉输出处于关闭状态（仅供Foxglove观察）')
            return

        # 发送VISION_POSITION_ESTIMATE（带covariance和真实姿态，9字段MAVLink2定义）
        try:
            self.maybe_send_heading_reset(yaw, now)
            if self.fatal_latched:
                return

            # covariance: 6x6位姿协方差上三角（行主序）
            # 状态顺序: x,y,z,roll,pitch,yaw；对角索引: 0,6,11,15,18,20。
            cov = [0.0] * 21
            cov[0] = max(0.01, min(float(pose_cov[7]), 100.0))
            cov[6] = max(0.01, min(float(pose_cov[0]), 100.0))
            cov[11] = max(0.01, min(float(pose_cov[14]), 100.0))
            cov[15] = 0.04
            cov[18] = 0.04
            cov[20] = 0.25

            vision_usec = (int(msg.header.stamp.sec) * 1_000_000 +
                           int(msg.header.stamp.nanosec) // 1_000)
            if vision_usec <= 0:
                vision_usec = int(now * 1e6)

            # 用v20.common方言（9字段定义，含covariance）
            v20_mav = mavlink_v20.MAVLink(
                None, srcSystem=self.SYSTEM_ID, srcComponent=self.COMPONENT_ID)
            msg_out = mavlink_v20.MAVLink_vision_position_estimate_message(
                vision_usec,
                x_ned, y_ned, z_ned,
                roll, pitch, yaw,
                cov, self.reset_counter)
            buf = msg_out.pack(v20_mav)
            with self.master_lock:
                self.master.port.write(buf)
            self.send_count = getattr(self, 'send_count', 0) + 1
            if self.send_count % 300 == 0:
                self.get_logger().info(
                    f'已发送VISION_POSITION_ESTIMATE(姿态+协方差): '
                    f'第{self.send_count}条, {len(buf)}字节, [健康] '
                    f'x={x_ned:.2f} y={y_ned:.2f} z={z_ned:.2f} '
                    f'r={math.degrees(roll):.1f} p={math.degrees(pitch):.1f} '
                    f'y={math.degrees(yaw):.1f} max_var={max_position_variance:.4f}')
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
    try:
        rclpy.shutdown()
    except Exception:
        pass

if __name__ == '__main__':
    main()
