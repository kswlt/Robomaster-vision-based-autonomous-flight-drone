#!/usr/bin/env python3
import rclpy, json, threading, math
from rclpy.qos import QoSProfile, ReliabilityPolicy
from nav_msgs.msg import Odometry
from http.server import BaseHTTPRequestHandler, HTTPServer

points = []
MAXN = 40000
qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

def cb(m):
    t = m.header.stamp.sec + m.header.stamp.nanosec * 1e-9
    p = m.pose.pose.position
    q = m.pose.pose.orientation
    if len(points) and t - points[-1][0] < 0.005:
        return
    points.append([t, p.x, p.y, p.z, q.w, q.x, q.y, q.z])
    if len(points) > MAXN:
        del points[:len(points) - MAXN]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        if self.path.startswith('/api'):
            t0 = points[0][0] if points else 0.0
            body = json.dumps({'t0': t0, 'pts': points}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            try:
                html = open('/tmp/viz_web/index.html', 'rb').read()
            except Exception:
                html = b'no index.html'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)

rclpy.init()
node = rclpy.create_node('viz_web')
node.create_subscription(Odometry, '/odomimu', cb, qos)
th = threading.Thread(target=lambda: rclpy.spin(node), daemon=True)
th.start()
print('viz_web on :8080', flush=True)
HTTPServer(('0.0.0.0', 8080), H).serve_forever()
