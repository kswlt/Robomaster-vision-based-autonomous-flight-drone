# -*- coding: utf-8 -*-
"""Deploy step 5: clean slate - kill all instances, start exactly one, full verification."""
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

steps = []

# 1. Diagnose everything
c = connect()
o, e = run(c, "ps -ef | grep -E 'python3|web_vis' | grep -v grep; echo ===; ss -tlnp | grep 8080", t=30)
steps.append("BEFORE:\n" + o + ("\n[err] " + e if e else ""))
c.close()

# 2. Kill everything web_vis / stale python launchers
c = connect()
o, e = run(c, "pkill -9 -f 'web_vis.py'; pkill -9 -f 'setsid nohup'; sleep 2; echo KILLED; ps -ef | grep -E 'web_vis|python3 -u' | grep -v grep | wc -l", t=30)
steps.append("KILL:\n" + o + ("\n[err] " + e if e else ""))
c.close()

# 3. Start exactly one
c = connect()
try:
    _, out, err = c.exec_command(
        "cd ~/kswlt_e2d && setsid nohup python3 -u web_vis.py > web_vis.log 2>&1 < /dev/null & echo LAUNCHED",
        timeout=6,
    )
    try:
        la = out.read().decode("utf-8", "replace").strip()
        steps.append("LAUNCH: " + la)
    except Exception as ex:
        steps.append("LAUNCH: channel held (expected) - " + type(ex).__name__)
except Exception as ex:
    steps.append("LAUNCH exception: " + type(ex).__name__ + " " + str(ex)[:100])
c.close()

time.sleep(10)

# 4. Full verification
c = connect()
o, e = run(c, "ps -ef | grep -E 'python3 -u web_vis' | grep -v grep; echo ===; curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:8080/; echo; echo ===; tail -8 ~/kswlt_e2d/web_vis.log; echo ===; grep -c 'Address already in use' ~/kswlt_e2d/web_vis.log", t=40)
steps.append("AFTER:\n" + o + ("\n[err] " + e if e else ""))
c.close()

print("\n\n".join(steps))
print("\nALL_DONE")
