"""Test ONNX inference on Orange Pi 5."""
import sys
sys.path.insert(0, '.')
from opi5_ssh import connect

def test_inference():
    client = connect()

    # Check ONNX model exists
    print("=== Check model files ===")
    stdin, stdout, stderr = client.exec_command(
        "ls -la ~/kswlt_e2d/repo/deployment/onnx/ 2>&1"
    )
    print(stdout.read().decode())

    # Write test script
    test_script = '''
import sys
sys.path.insert(0, "/home/orangepi/kswlt_e2d/repo")
import numpy as np
import time

# Test ONNX Runtime
try:
    import onnxruntime as ort
    print(f"onnxruntime: {ort.__version__}")
except ImportError as e:
    print(f"onnxruntime import failed: {e}")
    sys.exit(1)

model_path = "/home/orangepi/kswlt_e2d/repo/deployment/onnx/policy.onnx"
try:
    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    print(f"Model loaded: {model_path}")
    for inp in sess.get_inputs():
        print(f"  Input: {inp.name} shape={inp.shape} dtype={inp.type}")
    for out in sess.get_outputs():
        print(f"  Output: {out.name} shape={out.shape} dtype={out.type}")
except Exception as e:
    print(f"Model load failed: {e}")
    sys.exit(1)

# Benchmark
print("\\n=== Benchmark (100 iters) ===")
input_names = [i.name for i in sess.get_inputs()]
feed = {}
if len(input_names) >= 1:
    feed[input_names[0]] = np.random.rand(1, 1, 12, 16).astype(np.float32)
if len(input_names) >= 2:
    feed[input_names[1]] = np.random.rand(1, 10).astype(np.float32)
if len(input_names) >= 3:
    feed[input_names[2]] = np.random.rand(1, 192).astype(np.float32)

# Warmup
for _ in range(10):
    sess.run(None, feed)

# Benchmark
latencies = []
for _ in range(100):
    t0 = time.perf_counter()
    outputs = sess.run(None, feed)
    latencies.append((time.perf_counter() - t0) * 1000)

print(f"  Mean: {np.mean(latencies):.2f} ms")
print(f"  Std:  {np.std(latencies):.2f} ms")
print(f"  P95:  {np.percentile(latencies, 95):.2f} ms")
print(f"  FPS:  {1000/np.mean(latencies):.1f}")
print(f"  Output shape: {outputs[0].shape}")
print(f"  Output sample: {outputs[0].flatten()[:6]}")
'''

    # Upload and run
    sftp = client.open_sftp()
    with sftp.file("/home/orangepi/kswlt_e2d/test_onnx.py", "w") as f:
        f.write(test_script)
    sftp.close()

    print("\n=== Running inference test ===")
    stdin, stdout, stderr = client.exec_command(
        "cd ~/kswlt_e2d && python3 test_onnx.py 2>&1",
        timeout=60
    )
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print(f"[stderr]\n{err}")

    client.close()

if __name__ == "__main__":
    test_inference()
