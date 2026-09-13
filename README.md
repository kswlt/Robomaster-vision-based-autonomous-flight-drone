# RoboMaster Vision-Based Autonomous Flight Drone — E2E-RL

End-to-end reinforcement learning for a small RoboMaster drone to **actively impact a designated enemy armor plate** in the official RMUC 2026 arena.

> **This branch (E2E-RL) was completely rebuilt.** All legacy ROS2 / VIO / Jetson / PX4 code is discarded. The final compute platform is **RK3588**, not Jetson Orin NX.

## Project Goal

```
HOME → takeoff → high-speed flight to fixed enemy armor plate → ACTIVE IMPACT
→ HIT = SUCCESS (hitting other structures = FAILURE) → recover → return HOME
```

Core policy:
```
Depth Image + relative target position/direction + body velocity
+ attitude/gravity direction + GRU hidden state
    ↓
CNN + GRU Policy
    ↓
High-level control output (velocity / acceleration / thrust vector / yaw)
    ↓
Flight controller
```

**Not** RGB→PWM. The network never outputs four motor PWM directly.

## Architecture

- **Training**: DiffPhysDrone (differentiable physics, CUDA) in WSL2 — high episode throughput
- **Validation**: Isaac Sim (Windows native, headless) — independent simulator with real RM STL geometry, depth camera, rigid-body contact
- **Deployment**: PyTorch checkpoint → ONNX → RKNN → RK3588 inference

Training and validation are deliberately separated (different simulators) to detect sim-to-sim gaps before hardware.

## Directory Structure

```
├── assets/           # STL arena, armor reference images, manifests, analysis
├── configs/          # arena, armor, drone, depth_camera, training, evaluation, rk3588
├── sim/isaac/        # Isaac Sim scene, drone, armor target, depth camera, evaluation
├── training/         # DiffPhys upstream, adapter, target env, policy
├── deployment/       # ONNX export, RK3588 RKNN export/inference/benchmark
├── scripts/          # environment check, setup, run scripts (PowerShell)
├── tests/            # unit and integration tests
├── results/          # eval metrics, checkpoints, logs
└── docs/             # architecture, environment, assets, decisions, handoff
```

## Quick Start

### 1. Environment audit
```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_environment.ps1
```

### 2. Run headless evaluation (scripted baseline)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 20
```

### 3. DiffPhys training (WSL2)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_diffphys_wsl.ps1
```

## Key Constraints

- Isaac Sim 6.1.0 Windows standalone (Omniverse Launcher deprecated Oct 2025)
- Arena unit = **meters** (RMUC 2026 battlefield: 28m × 15m, 2.4m walls)
- ArmorTarget is an **independent collider** (not part of arena mesh)
- Policy: small CNN + GRU + MLP (RK3588-friendly, ONNX-exportable)
- INT8 quantization is **not** default; FP32/FP16/INT8 must be compared

## Milestones

| # | Milestone | Status |
|---|-----------|--------|
| 1 | Isaac headless: STL + drone + depth + scripted hit, 20 ep 100% | In progress |
| 2 | DiffPhys original training runs in WSL2 GPU | Pending |
| 3 | Target-impact policy: 1000 randomized episodes | Pending |
| 4 | Checkpoint → Isaac, 1000 episodes with metrics | Pending |
| 5 | Depth noise + domain rand, ONNX export, RK3588 suitability | Pending |

See `docs/CURRENT_STATE.md` for live status and `docs/HANDOFF.md` to hand off.
