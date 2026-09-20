# -*- coding: utf-8 -*-
"""Deploy dashboard keyboard-visualization update: upload, compile-check, clean restart, verify data path."""
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
    return o.strip(), e.strip()

# 1. Upload
c = connect()
sftp = c.open_sftp()
sftp.put(LOCAL, REMOTE)
sftp.close()
print("== uploaded ==")
c.close()

# 2. Verify md5 on board matches local (handoff known-issue #4), then compile-check
import hashlib
local_md5 = hashlib.md5(open(LOCAL, "rb").read()).hexdigest()
print("local md5:", local_md5)
c = connect()
o, e = run(c, "md5sum ~/kswlt_e2d/web_vis.py; python3 -m py_compile ~/kswlt_e2d/web_vis.py && echo COMPILE_OK", t=60)
print(o, e[:200])
if local_md5 not in o:
    c.close()
    raise SystemExit("MD5 MISMATCH OR COMPILE FAILED - aborted")
c.close()

# 3. Clean restart
c = connect()
o, e = run(c, "pkill -9 -f 'web_vis.py'; pkill -9 -f 'setsid nohup'; sleep 2; echo CLEANED", t=30)
print(o, e[:200])
c.close()

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

# 4. Verify: HTTP, status fields, HTML markers, then simulate a key command and re-read /status
c = connect()
o, e = run(c,
    "curl -s -o /dev/null -w 'HTTP %{http_code}\\n' http://localhost:8080/; "
    "curl -s http://localhost:8080/status | python3 -c \"import sys,json; s=json.load(sys.stdin); print('key_active=', s['key_active'], 'key_cmd=', s['key_cmd'])\"; "
    "curl -s http://localhost:8080/ | grep -c -e 'key-cmd-line' -e 'updateKeyIndicator' -e 'k-w' -e '光流'; "
    "curl -s -X POST -H 'Content-Type: application/json' -d '{\"vx\":0.5,\"vy\":-0.5,\"vz\":-0.35}' http://localhost:8080/key_update >/dev/null; sleep 1; "
    "curl -s http://localhost:8080/status | python3 -c \"import sys,json; s=json.load(sys.stdin); print('after_update key_cmd=', s['key_cmd'])\"; "
    "curl -s -X POST -H 'Content-Type: application/json' -d '{\"vx\":0,\"vy\":0,\"vz\":0}' http://localhost:8080/key_update >/dev/null; "
    "grep -c 'Address already in use' ~/kswlt_e2d/web_vis.log", t=60)
print(o, e[:300])
c.close()
print("DONE")
