"""Kill process, reset camera, restart."""
import sys
sys.path.insert(0, '.')
from opi5_ssh import connect
import time

client = connect()

# Kill
print("=== Killing existing processes ===")
stdin, stdout, stderr = client.exec_command("pkill -9 -f 'python3 main'; sleep 2; echo done")
print(stdout.read().decode())

# Reset RealSense
print("=== Resetting RealSense ===")
reset_script = '''
import pyrealsense2 as rs
ctx = rs.context()
devs = ctx.query_devices()
print(f"Devices: {len(devs)}")
for d in devs:
    print(f"  {d.get_info(rs.camera_info.name)}")
    try:
        d.hardware_reset()
        print("  Hardware reset OK")
    except Exception as e:
        print(f"  Reset error: {e}")
'''
sftp = client.open_sftp()
with sftp.file("/home/orangepi/kswlt_e2d/reset_cam.py", "w") as f:
    f.write(reset_script)
sftp.close()

stdin, stdout, stderr = client.exec_command("cd ~/kswlt_e2d && python3 reset_cam.py 2>&1")
print(stdout.read().decode())
print(stderr.read().decode())

time.sleep(3)

# Restart
print("=== Restarting main.py ===")
cmd = ("cd ~/kswlt_e2d && nohup python3 main.py --mode ground "
       "--foxglove-port 8766 > flight.log 2>&1 & echo $!")
stdin, stdout, stderr = client.exec_command(cmd)
pid = stdout.read().decode().strip()
print(f"PID: {pid}")

time.sleep(12)

# Check log
print("=== Log after 12s ===")
stdin, stdout, stderr = client.exec_command("cat ~/kswlt_e2d/flight.log")
print(stdout.read().decode())
print(stderr.read().decode())

# Check process
stdin, stdout, stderr = client.exec_command("ps aux | grep 'python3 main' | grep -v grep | wc -l")
print(f"Processes running: {stdout.read().decode().strip()}")

client.close()
