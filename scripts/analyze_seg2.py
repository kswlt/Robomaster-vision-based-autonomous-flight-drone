#!/usr/bin/env python3
import sys, rosbag2_py, numpy as np, yaml, re
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
path = sys.argv[1]; logf = sys.argv[2]
meta = yaml.safe_load(open(path + '/metadata.yaml').read())['rosbag2_bagfile_information']
reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=path, storage_id=meta['storage_identifier']), rosbag2_py.ConverterOptions('', ''))
types = {x.name: get_message(x.type) for x in reader.get_all_topics_and_types()}
reader.set_filter(rosbag2_py.StorageFilter(topics=['/odomimu']))
odom = []
while reader.has_next():
    topic, data, arrival = reader.read_next()
    m = deserialize_message(data, types[topic])
    t = m.header.stamp.sec + m.header.stamp.nanosec*1e-9
    p = m.pose.pose.position; v = m.twist.twist.linear
    odom.append([t, p.x, p.y, p.z, v.x, v.y, v.z])
odom = np.array(odom)
t0 = odom[0,0]; trel = odom[:,0] - t0
print('n=%d t0=%.3f last=%.2f' % (len(odom), t0, trel[-1]))
segs = [('static_0_49',0,49.5),('yaw_50_59',50,59.5),('static_60_61',60,61.5),
        ('pitch_62_70',62,70.5),('trans_71_87',71,87.5),('static_88_149',88,149)]
for name, a, b in segs:
    m = (trel >= a) & (trel < b); o = odom[m]
    if len(o) < 2:
        print(' %s: NO DATA' % name); continue
    d0 = o[0][1:4]; d1 = o[-1][1:4]
    disp = float(np.linalg.norm(d1-d0))
    mx = float(max(np.linalg.norm(o[i,1:4]-d0) for i in range(len(o))))
    vm = float(np.linalg.norm(o[:,4:7],axis=1).max())
    print(' %s: n=%d t=[%.1f,%.1f] p0=(%.2f,%.2f,%.2f) p1=(%.2f,%.2f,%.2f) disp=%.3f max=%.3f |v|max=%.3f' % (name, len(o), trel[m][0], trel[m][-1], d0[0],d0[1],d0[2], d1[0],d1[1],d1[2], disp, mx, vm))
fin = odom[-1]
print(' FINAL t=%.1f p=(%.2f,%.2f,%.2f) |p|=%.2f' % (trel[-1], fin[1],fin[2],fin[3], np.linalg.norm(fin[1:4])))
print(' max|p|=%.2f at t=%.1f' % (np.linalg.norm(odom[:,1:4],axis=1).max(), trel[np.linalg.norm(odom[:,1:4],axis=1).argmax()]))
bias = re.findall(r'bg = ([\-0-9., ]+?) \| ba = ([\-0-9., ]+?)\n', open(logf).read())
if bias:
    ba = np.array([[float(x) for x in s.split(',')] for s in [b[1] for b in bias]])
    bg = np.array([[float(x) for x in s.split(',')] for s in [b[0] for b in bias]])
    T = trel[-1]; ti = np.linspace(0, T, len(ba))
    print(' ba first:', ba[0].tolist())
    for th in [0.02, 0.05, 0.10]:
        for j, nm in zip(range(3), ['x','y','z']):
            idx = np.where(np.abs(ba[:,j]) > th)[0]
            if len(idx): print(' |ba_%s|>%.2f first at t~%.1f (ba=%s)' % (nm, th, ti[idx[0]], ba[idx[0]].tolist()))
    for name, a, b in segs:
        mm = (ti >= a) & (ti < b)
        if mm.sum(): print(' ba mean %s: %s' % (name, ba[mm].mean(axis=0).tolist()))
