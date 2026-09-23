#!/usr/bin/env python3
import rosbag2_py, os, shutil
from rclpy.serialization import deserialize_message, serialize_message
from rosidl_runtime_py.utilities import get_message

SRC = '/home/orangepi/vio_data/20260922T191022_360Z_DYN50E/bag'
DST = '/home/orangepi/vio_data/DYN50E_fixedts'
SLOPE = -0.000908
shutil.rmtree(DST, ignore_errors=True)
os.makedirs(DST)

reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=SRC, storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
topics = reader.get_all_topics_and_types()
print('topics:', topics)
msg_types = {}
for t in topics:
    msg_types[t.name] = get_message(t.type)

writer = rosbag2_py.SequentialWriter()
writer.open(rosbag2_py.StorageOptions(uri=DST + '/bag', storage_id='sqlite3'), rosbag2_py.ConverterOptions('', ''))
for t in topics:
    writer.create_topic(rosbag2_py.TopicMetadata(name=t.name, type=t.type, serialization_format=t.serialization_format))

first = None
n = 0
while reader.has_next():
    topic, data, arrival = reader.read_next()
    m = deserialize_message(data, msg_types[topic])
    t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    if first is None:
        first = t
    if topic == '/imu':
        trel = t - first
        fix = abs(SLOPE) * trel
        tf = t + fix
        m.header.stamp.sec = int(tf)
        m.header.stamp.nanosec = int(round((tf - int(tf)) * 1e9))
        data = serialize_message(m)
    writer.write(topic, data, arrival if arrival else int(t * 1e9))
    n += 1
print('rewrote %d messages; first=%.3f last=%.3f' % (n, first, t))
