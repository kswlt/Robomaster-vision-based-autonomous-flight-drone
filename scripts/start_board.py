# -*- coding: utf-8 -*-
"""Standard board startup (handoff section 3): stop VIO, clean stale processes, start web_vis.py, verify."""
import time
import paramiko

HOST = "192.168.1.215"
USER = "orangepi"
PASS = "orangepi"

def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASS, timeout=15)
    return c

def run(c, cmd, t=30):
    _, out, err = c.exec_command(cmd, timeout=t)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    return o.strip(), e.strip()

print("== pre-check ==")
c = connect()
o, e = run(c, "echo orangepi | sudo -S systemctl is-active vio.service watchdog_camera.service vio-watchdog.service 2>/dev/null; ps -ef | grep 'python3 -u web_vis' | grep -v grep | wc -l; ls /dev/ttyACM0 /dev/video0 2>&1", t=30)
print(o, e[:200])
c.close()

print("== stop VIO + stale processes ==")
c = connect()
o, e = run(c,
    "echo orangepi | sudo -S systemctl stop vio.service watchdog_camera.service vio-watchdog.service 2>/dev/null; "
    "echo orangepi | sudo -S pkill -9 -f realsense2_camera 2>/dev/null; "
    "pkill -9 -f 'web_vis.py'; pkill -9 -f 'setsid nohup'; sleep 2; echo DONE", t=40)
print(o, e[:200])
c.close()

print("== launch ==")
c = connect()
try:
    _, out, err = c.exec_command(
        "cd ~/kswlt_e2d && setsid nohup python3 -u web_vis.py > web_vis.log 2>&1 < /dev/null & echo LAUNCHED",
        timeout=6,
    )
    try:
        print("launch:", out.read().decode("utf-8", "replace").strip())
    except Exception:
        print("launch: channel held (expected)")
except Exception as ex:
    print("launch exception:", type(ex).__name__, str(ex)[:100])
c.close()

time.sleep(10)

print("== verify ==")
c = connect()
o, e = run(c,
    "ps -ef | grep 'python3 -u web_vis' | grep -v grep; "
    "curl -s -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:8080/; "
    "tail -6 ~/kswlt_e2d/web_vis.log; "
    "grep -c 'Address already in use' ~/kswlt_e2d/web_vis.log", t=40)
print(o, e[:300])
c.close()
print("DONE")
