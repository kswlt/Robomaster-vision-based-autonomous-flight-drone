# -*- coding: utf-8 -*-
"""Deploy the keyboard-completed web_vis.py to the Orange Pi and restart it (handoff section 3 flow)."""
import time
import paramiko

HOST = "192.168.1.215"
USER = "orangepi"
PASS = "orangepi"
LOCAL = r"C:\Users\Admin\Desktop\端到端强化学习无人机仿真\web_vis_board.py"
REMOTE = "/home/orangepi/kswlt_e2d/web_vis.py"

def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASS, timeout=15)
    return c

def run(c, cmd, t=30):
    _, out, err = c.exec_command(cmd, timeout=t)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    return code, o, e

c = connect()

# 1. Upload
print("== upload ==")
sftp = c.open_sftp()
sftp.put(LOCAL, REMOTE)
sftp.close()
print("uploaded")

# 2. Verify on board (handoff known-issue #4: sftp may corrupt, must py_compile)
print("== py_compile on board ==")
code, o, e = run(c, "cd ~/kswlt_e2d && python3 -m py_compile web_vis.py && echo COMPILE_OK", t=60)
print(o.strip(), e.strip()[:300])
if "COMPILE_OK" not in o:
    print("COMPILE FAILED - aborting, not touching the running system")
    c.close()
    raise SystemExit(1)

# 3. Grep the three endpoints + handlers as a sanity check
print("== endpoint sanity ==")
code, o, e = run(c, "grep -c 'key_start' ~/kswlt_e2d/web_vis.py; grep -c 'key_update' ~/kswlt_e2d/web_vis.py; grep -c 'if cmd_key_start' ~/kswlt_e2d/web_vis.py; grep -c 'addEventListener' ~/kswlt_e2d/web_vis.py")
print(o.strip())

# 4. Stop VIO (occupies the camera), kill stale processes, start web_vis.py (handoff section 3)
print("== stop VIO + start ==")
code, o, e = run(c,
    "echo orangepi | sudo -S systemctl stop vio.service watchdog_camera.service vio-watchdog.service 2>/dev/null; "
    "echo orangepi | sudo -S pkill -9 -f realsense2_camera 2>/dev/null; "
    "pkill -9 -f web_vis.py 2>/dev/null; sleep 1; "
    "cd ~/kswlt_e2d && setsid bash -c 'python3 -u web_vis.py > web_vis.log 2>&1' < /dev/null & disown; echo STARTED", t=40)
print(o.strip(), e.strip()[:300])

# 5. Wait and verify
time.sleep(8)
print("== verify ==")
code, o, e = run(c, "curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8080/; echo '--- log tail ---'; tail -6 ~/kswlt_e2d/web_vis.log")
print(o.strip(), e.strip()[:300])

c.close()
print("DONE")
