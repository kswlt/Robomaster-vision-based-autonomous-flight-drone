#!/usr/bin/env python3
"""
Lightweight system monitor for Orange Pi 5 / RK3588.
Publishes CPU and memory usage to ROS2 topics for Foxglove visualization.

Topics:
  /system/cpu_usage  (std_msgs/Float32)  - CPU usage percent (0-100)
  /system/mem_usage  (std_msgs/Float32)  - Memory usage percent (0-100)
  /system/cpu_temp   (std_msgs/Float32)  - SoC temperature (Celsius, if available)
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
import time
import os


class SystemMonitor(Node):
    def __init__(self):
        super().__init__('system_monitor')
        self.cpu_pub = self.create_publisher(Float32, '/system/cpu_usage', 10)
        self.mem_pub = self.create_publisher(Float32, '/system/mem_usage', 10)
        self.temp_pub = self.create_publisher(Float32, '/system/cpu_temp', 10)
        self.timer = self.create_timer(1.0, self.publish_stats)  # 1 Hz
        self.prev_idle = None
        self.prev_total = None
        self.get_logger().info('System monitor started (1 Hz)')

    def read_cpu(self):
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        parts = line.split()
        # user, nice, system, idle, iowait, irq, softirq, steal
        idle = int(parts[4]) + int(parts[5])
        total = sum(int(x) for x in parts[1:])
        return idle, total

    def get_cpu_usage(self):
        idle, total = self.read_cpu()
        if self.prev_idle is None:
            self.prev_idle = idle
            self.prev_total = total
            return 0.0
        idle_delta = idle - self.prev_idle
        total_delta = total - self.prev_total
        self.prev_idle = idle
        self.prev_total = total
        if total_delta == 0:
            return 0.0
        usage = (1.0 - idle_delta / total_delta) * 100.0
        return max(0.0, min(100.0, usage))

    def get_mem_usage(self):
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        mem_total = 0
        mem_available = 0
        for line in lines:
            if line.startswith('MemTotal:'):
                mem_total = int(line.split()[1])
            elif line.startswith('MemAvailable:'):
                mem_available = int(line.split()[1])
        if mem_total == 0:
            return 0.0
        usage = (1.0 - mem_available / mem_total) * 100.0
        return max(0.0, min(100.0, usage))

    def get_cpu_temp(self):
        # RK3588 thermal zones
        temp_paths = [
            '/sys/class/thermal/thermal_zone0/temp',
            '/sys/class/thermal/thermal_zone1/temp',
            '/sys/class/thermal/thermal_zone2/temp',
        ]
        temps = []
        for p in temp_paths:
            try:
                with open(p, 'r') as f:
                    t = int(f.read().strip()) / 1000.0
                    if 0 < t < 120:
                        temps.append(t)
            except (IOError, ValueError):
                pass
        if temps:
            return sum(temps) / len(temps)
        return 0.0

    def publish_stats(self):
        cpu = self.get_cpu_usage()
        mem = self.get_mem_usage()
        temp = self.get_cpu_temp()

        cpu_msg = Float32()
        cpu_msg.data = cpu
        self.cpu_pub.publish(cpu_msg)

        mem_msg = Float32()
        mem_msg.data = mem
        self.mem_pub.publish(mem_msg)

        if temp > 0:
            temp_msg = Float32()
            temp_msg.data = temp
            self.temp_pub.publish(temp_msg)


def main(args=None):
    rclpy.init(args=args)
    node = SystemMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
