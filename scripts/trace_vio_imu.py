#!/usr/bin/env python3
"""Diagnostic subclass: trace existing bridge mapping without changing its math."""
import csv
import importlib.util
import os
import time
import rclpy

spec = importlib.util.spec_from_file_location('runtime_bridge', '/home/orangepi/vio_ws/vio_bridge/vio_bridge_combined.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class TracedBridge(runtime.VIOBridge):
    def __init__(self):
        self.trace_file = open(os.environ['VIO_IMU_TRACE'], 'x', buffering=65536)
        self.trace = csv.writer(self.trace_file)
        self.trace.writerow(['host_before_ns','monotonic_ns','sensor_usec','mapped_sec','mapped_nanosec',
                             'mapping_offset_sec','gyro_x_frd','gyro_y_frd','gyro_z_frd',
                             'accel_x_frd','accel_y_frd','accel_z_frd'])
        self.last_trace_flush = time.monotonic()
        super().__init__()
        if self.send_vision_to_px4:
            raise RuntimeError('Diagnostic capture requires send_vision_to_px4=false')

    def imu_timestamp(self, msg):
        host = self.get_clock().now().nanoseconds
        mono = time.monotonic_ns()
        stamp = super().imu_timestamp(msg)
        self.trace.writerow([host,mono,msg.time_usec,*stamp,self.imu_clock_offset,
                             msg.xgyro,msg.ygyro,msg.zgyro,msg.xacc,msg.yacc,msg.zacc])
        if time.monotonic()-self.last_trace_flush > 1:
            self.trace_file.flush()
            self.last_trace_flush = time.monotonic()
        return stamp


if __name__ == '__main__':
    rclpy.init()
    node = TracedBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.running = False
        node.trace_file.flush()
        # Process shutdown owns the reader thread; avoid closing its CSV mid-write.
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
