#!/usr/bin/env python3
"""
Enhanced system monitor for Orange Pi 5 / RK3588.
Publishes detailed CPU/memory metrics to ROS2 topics for Foxglove visualization.

Topics:
  /system/cpu_usage       (std_msgs/Float32)         - Overall CPU usage % (all cores avg)
  /system/cpu_per_core    (std_msgs/Float32MultiArray)- Per-core CPU usage % [core0..core7]
  /system/cpu_freq_big    (std_msgs/Float32)         - Big cluster (A76) freq GHz
  /system/cpu_freq_little (std_msgs/Float32)         - Little cluster (A55) freq GHz
  /system/mem_usage       (std_msgs/Float32)         - Memory usage %
  /system/cpu_temp        (std_msgs/Float32)         - SoC temperature C
  /system/load_avg        (std_msgs/Float32)         - 1-min load average
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Float32MultiArray
import os
import time


class SystemMonitor(Node):
    def __init__(self):
        super().__init__('system_monitor')
        # Publishers
        self.cpu_pub = self.create_publisher(Float32, '/system/cpu_usage', 10)
        self.cpu_per_core_pub = self.create_publisher(Float32MultiArray, '/system/cpu_per_core', 10)
        self.cpu_freq_big_pub = self.create_publisher(Float32, '/system/cpu_freq_big', 10)
        self.cpu_freq_little_pub = self.create_publisher(Float32, '/system/cpu_freq_little', 10)
        self.mem_pub = self.create_publisher(Float32, '/system/mem_usage', 10)
        self.temp_pub = self.create_publisher(Float32, '/system/cpu_temp', 10)
        self.load_pub = self.create_publisher(Float32, '/system/load_avg', 10)

        # 5 Hz publish rate (was 1 Hz)
        self.timer = self.create_timer(0.2, self.publish_stats)

        # CPU tracking
        self.prev_total = None
        self.prev_idle = None
        self.prev_core_total = []
        self.prev_core_idle = []

        self.get_logger().info('Enhanced system monitor started (5 Hz)')

    def read_cpu_overall(self):
        with open('/proc/stat', 'r') as f:
            line = f.readline()
        parts = line.split()
        idle = int(parts[4]) + int(parts[5])
        total = sum(int(x) for x in parts[1:])
        return idle, total

    def read_cpu_per_core(self):
        cores = []
        with open('/proc/stat', 'r') as f:
            for line in f:
                if line.startswith('cpu') and not line.startswith('cpu '):
                    parts = line.split()
                    idle = int(parts[4]) + int(parts[5])
                    total = sum(int(x) for x in parts[1:])
                    cores.append((idle, total))
        return cores

    def get_cpu_usage(self):
        idle, total = self.read_cpu_overall()
        if self.prev_total is None:
            self.prev_idle = idle
            self.prev_total = total
            return 0.0
        idle_delta = idle - self.prev_idle
        total_delta = total - self.prev_total
        self.prev_idle = idle
        self.prev_total = total
        if total_delta == 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0))

    def get_cpu_per_core(self):
        cores = self.read_cpu_per_core()
        n = len(cores)
        if not self.prev_core_total:
            self.prev_core_idle = [c[0] for c in cores]
            self.prev_core_total = [c[1] for c in cores]
            return [0.0] * n

        usages = []
        for i, (idle, total) in enumerate(cores):
            idle_delta = idle - self.prev_core_idle[i]
            total_delta = total - self.prev_core_total[i]
            self.prev_core_idle[i] = idle
            self.prev_core_total[i] = total
            if total_delta == 0:
                usages.append(0.0)
            else:
                usages.append(max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0)))
        return usages

    def get_cpu_freq(self):
        big_freq = 0.0
        little_freq = 0.0
        # RK3588: cpu0-3 = A55 little, cpu4-7 = A76 big
        try:
            with open('/sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq', 'r') as f:
                big_freq = int(f.read().strip()) / 1000000.0
        except (IOError, ValueError):
            pass
        try:
            with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', 'r') as f:
                little_freq = int(f.read().strip()) / 1000000.0
        except (IOError, ValueError):
            pass
        return big_freq, little_freq

    def get_mem_usage(self):
        mem_total = 0
        mem_available = 0
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1])
        if mem_total == 0:
            return 0.0
        return max(0.0, min(100.0, (1.0 - mem_available / mem_total) * 100.0))

    def get_cpu_temp(self):
        temps = []
        for i in range(6):
            p = f'/sys/class/thermal/thermal_zone{i}/temp'
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

    def get_load_avg(self):
        try:
            with open('/proc/loadavg', 'r') as f:
                return float(f.read().split()[0])
        except (IOError, ValueError, IndexError):
            return 0.0

    def publish_stats(self):
        cpu = self.get_cpu_usage()
        per_core = self.get_cpu_per_core()
        big_freq, little_freq = self.get_cpu_freq()
        mem = self.get_mem_usage()
        temp = self.get_cpu_temp()
        load = self.get_load_avg()

        # Overall CPU
        msg = Float32()
        msg.data = cpu
        self.cpu_pub.publish(msg)

        # Per-core CPU
        pc_msg = Float32MultiArray()
        pc_msg.data = per_core
        self.cpu_per_core_pub.publish(pc_msg)

        # CPU frequencies
        bf_msg = Float32()
        bf_msg.data = big_freq
        self.cpu_freq_big_pub.publish(bf_msg)

        lf_msg = Float32()
        lf_msg.data = little_freq
        self.cpu_freq_little_pub.publish(lf_msg)

        # Memory
        mem_msg = Float32()
        mem_msg.data = mem
        self.mem_pub.publish(mem_msg)

        # Temperature
        if temp > 0:
            temp_msg = Float32()
            temp_msg.data = temp
            self.temp_pub.publish(temp_msg)

        # Load average
        load_msg = Float32()
        load_msg.data = load
        self.load_pub.publish(load_msg)


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
