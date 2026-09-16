"""Deploy project to Orange Pi 5 via SSH."""
import sys
sys.path.insert(0, '.')
from opi5_ssh import connect, run

def deploy():
    client = connect()

    # Step 1: Clone repo
    print("=== Cloning repo ===")
    cmd = "cd ~/kswlt_e2d && rm -rf repo && git clone --depth 1 -b E2E-RL https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone.git repo 2>&1"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    print(stdout.read().decode())
    print(stderr.read().decode())

    # Step 2: List files
    print("\n=== Repo contents ===")
    stdin, stdout, stderr = client.exec_command("ls -la ~/kswlt_e2d/repo/")
    print(stdout.read().decode())

    # Step 3: Install Python deps
    print("\n=== Installing Python deps ===")
    cmd = "pip3 install --user onnxruntime opencv-python-headless 2>&1 | tail -10"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=180)
    print(stdout.read().decode())
    print(stderr.read().decode())

    # Step 4: Try rknnlite
    print("\n=== Installing rknnlite2 ===")
    cmd = "pip3 install --user rknnlite2 2>&1 | tail -5"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    print(stdout.read().decode())
    print(stderr.read().decode())

    client.close()
    print("\n=== Deploy complete ===")

if __name__ == "__main__":
    deploy()
