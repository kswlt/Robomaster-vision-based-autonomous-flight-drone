"""Start ground test on Orange Pi 5 in background."""
import sys
sys.path.insert(0, '.')
from opi5_ssh import connect

client = connect()

# Kill any existing instance
stdin, stdout, stderr = client.exec_command("pkill -f 'python3 main.py' 2>/dev/null; sleep 1; echo 'killed'")
print(stdout.read().decode())

# Start in background with nohup, redirect output to log
cmd = ("cd ~/kswlt_e2d && nohup python3 main.py --mode ground "
       "--foxglove-port 8766 > flight.log 2>&1 & echo $!")
stdin, stdout, stderr = client.exec_command(cmd)
pid = stdout.read().decode().strip()
print(f"Started with PID: {pid}")

# Wait a bit then check log
import time
time.sleep(5)

stdin, stdout, stderr = client.exec_command("cat ~/kswlt_e2d/flight.log")
print("=== Log (first 50 lines) ===")
print(stdout.read().decode()[:3000])
print(stderr.read().decode()[:1000])

# Check if process is running
stdin, stdout, stderr = client.exec_command(f"ps aux | grep {pid} | grep -v grep")
print("=== Process status ===")
print(stdout.read().decode())

# Check Foxglove port
stdin, stdout, stderr = client.exec_command("ss -tlnp | grep 8765")
print("=== Foxglove port ===")
print(stdout.read().decode())

client.close()
