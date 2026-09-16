"""Upload main.py and start with sim-depth."""
import sys
sys.path.insert(0, '.')
from opi5_ssh import connect
import time

client = connect()

# Upload
sftp = client.open_sftp()
sftp.put('../deployment/rk3588/main.py', '/home/orangepi/kswlt_e2d/main.py')
sftp.close()
print("Uploaded main.py")

# Kill existing
stdin, stdout, stderr = client.exec_command("pkill -9 -f 'python3 main'; sleep 1; echo killed")
print(stdout.read().decode())

# Start with sim-depth
cmd = ("cd ~/kswlt_e2d && nohup python3 main.py --mode ground "
       "--foxglove-port 8766 --sim-depth > flight.log 2>&1 & echo $!")
stdin, stdout, stderr = client.exec_command(cmd)
pid = stdout.read().decode().strip()
print(f"Started PID: {pid}")

time.sleep(10)

# Check log
stdin, stdout, stderr = client.exec_command("cat ~/kswlt_e2d/flight.log")
print("=== LOG ===")
print(stdout.read().decode())
print(stderr.read().decode())

# Check process
stdin, stdout, stderr = client.exec_command("ps aux | grep 'python3 main' | grep -v grep | wc -l")
print(f"Processes: {stdout.read().decode().strip()}")

# Check port
stdin, stdout, stderr = client.exec_command("ss -tlnp | grep 8766")
print(f"Port: {stdout.read().decode().strip()}")

client.close()
