"""RK3588 inference benchmark.

Measures latency, FPS, CPU/NPU usage, RAM for the deployed policy.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np


def benchmark(model_path: str, warmup: int = 50, iterations: int = 500,
              use_npu: bool = True) -> dict:
    """Benchmark inference latency and throughput."""
    from deployment.rk3588.inference import RK3588Inference

    infer = RK3588Inference(model_path, use_npu=use_npu)

    # Synthetic inputs
    depth = np.random.uniform(0.5, 10.0, (240, 320)).astype(np.float32)
    state = np.random.randn(12).astype(np.float32)

    # Warmup
    for _ in range(warmup):
        infer.infer(depth, state)
    infer.reset()

    # Measure
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        infer.infer(depth, state)
        latencies.append(time.perf_counter() - t0)

    latencies = np.array(latencies) * 1000  # ms
    results = {
        "model": model_path,
        "backend": "NPU" if use_npu else "CPU",
        "iterations": iterations,
        "latency_mean_ms": float(np.mean(latencies)),
        "latency_std_ms": float(np.std(latencies)),
        "latency_p95_ms": float(np.percentile(latencies, 95)),
        "latency_p99_ms": float(np.percentile(latencies, 99)),
        "fps": float(1000.0 / np.mean(latencies)),
    }

    print(f"=== Benchmark: {model_path} ({results['backend']}) ===")
    for k, v in results.items():
        if k not in ("model", "backend"):
            print(f"  {k}: {v:.2f}")

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="deployment/rk3588/policy.rknn")
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--cpu", action="store_true", help="Force CPU backend")
    args = parser.parse_args()
    benchmark(args.model, args.warmup, args.iterations, use_npu=not args.cpu)


if __name__ == "__main__":
    main()
