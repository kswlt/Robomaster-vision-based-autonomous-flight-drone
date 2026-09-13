# RK3588 Deployment

Final competition platform: **RK3588** (not Jetson Orin NX).

## Pipeline
```
PyTorch checkpoint → ONNX (opset 17) → RKNN (Toolkit2) → RK3588 NPU
```

## RK3588 Responsibilities
- Depth preprocessing
- Policy inference (CNN+GRU+MLP)
- Target info processing
- Armor visual detection (if needed)

## Flight Controller Responsibilities
- Attitude stabilization
- Low-level control loops
- Motor output

No training on device.

## Export
```powershell
powershell -ExecutionPolicy Bypass -File scripts/export_rk3588.ps1
```

## Quantization
INT8 is **NOT** default. Must compare FP32, FP16, INT8 on:
- Policy output MSE
- Task success rate
- Target hit rate

## GRU Handling
- Prefer NPU if RKNN supports it well
- Fall back to ARM CPU if NPU GRU support is poor

## Benchmark Metrics
latency_ms, fps, cpu_usage, npu_usage, ram_mb

## Current Status
Pipeline scaffolded (deployment/rk3588/export_rknn.py, inference.py, benchmark.py). Not executed (no trained policy yet).
