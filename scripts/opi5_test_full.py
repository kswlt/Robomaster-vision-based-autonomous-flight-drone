"""Full end-to-end inference test on Orange Pi 5."""
import sys
sys.path.insert(0, '.')
from opi5_ssh import connect

def test_full():
    client = connect()

    test_script = '''
import sys
sys.path.insert(0, "/home/orangepi/kswlt_e2d/repo")
import numpy as np
import time

# Test full RK3588Policy
try:
    from deployment.rk3588.inference import RK3588Policy
    print("RK3588Policy imported OK")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# Load policy (ONNX CPU mode)
policy = RK3588Policy(
    "/home/orangepi/kswlt_e2d/repo/deployment/onnx/policy.onnx",
    use_npu=False
)
policy.reset()

# Test with simulated depth (640x480 raw depth in meters)
print("\\n=== Full pipeline test (640x480 depth -> action) ===")
depth_raw = np.random.rand(480, 640).astype(np.float32) * 10 + 0.5  # 0.5-10.5m
pos = np.array([0.0, 0.0, 1.0], dtype=np.float32)
vel = np.array([1.0, 0.0, 0.0], dtype=np.float32)
yaw = 0.0
target = np.array([5.0, 0.0, 1.0], dtype=np.float32)

# Warmup
for _ in range(5):
    action = policy.infer(depth_raw, pos, vel, yaw, target)

# Benchmark full pipeline
latencies = []
for _ in range(100):
    action = policy.infer(depth_raw, pos, vel, yaw, target)
    latencies.append(action["latency_ms"])

print(f"  Full pipeline mean: {np.mean(latencies):.2f} ms")
print(f"  Full pipeline P95:  {np.percentile(latencies, 95):.2f} ms")
print(f"  Full pipeline FPS:  {1000/np.mean(latencies):.1f}")
print(f"  Output accel: {action['accel']}")
print(f"  Output yaw_rate: {action['yaw_rate']}")

# Depth preprocessing only
print("\\n=== Depth preprocessing only ===")
t0 = time.perf_counter()
for _ in range(100):
    d = policy.normalize_depth(depth_raw)
pre_ms = (time.perf_counter() - t0) / 100 * 1000
print(f"  Preprocess mean: {pre_ms:.2f} ms")
print(f"  Preprocessed shape: {d.shape}")
print(f"  Preprocessed range: [{d.min():.3f}, {d.max():.3f}]")

# State construction
print("\\n=== State construction ===")
state = policy.build_state(pos, vel, yaw, target)
print(f"  State shape: {state.shape}")
print(f"  State values: {state}")

print("\\n=== ALL TESTS PASSED ===")
'''

    sftp = client.open_sftp()
    with sftp.file("/home/orangepi/kswlt_e2d/test_full.py", "w") as f:
        f.write(test_script)
    sftp.close()

    stdin, stdout, stderr = client.exec_command(
        "cd ~/kswlt_e2d && python3 test_full.py 2>&1",
        timeout=60
    )
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err and "Warning" not in err:
        print(f"[stderr]\n{err}")

    client.close()

if __name__ == "__main__":
    test_full()
