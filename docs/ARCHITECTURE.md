# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   TRAINING (WSL2, GPU)                       │
│  DiffPhysDrone CUDA env  ──►  CNN+GRU+MLP Policy            │
│  (high throughput, differentiable)     │                    │
│                                        ▼                    │
│                                  PyTorch checkpoint          │
└────────────────────────────────────────┬────────────────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          ▼              ▼              ▼
                   ONNX export    Isaac Validator   RKNN export
                   (deployment)   (Windows, GPU)   (RK3588 NPU)
                          │              │              │
                          ▼              ▼              ▼
                   policy.onnx    Headless eval    policy.rknn
                                   1000 episodes    RK3588 inference
```

## Why Training ≠ Validation

| Aspect | Training (DiffPhys) | Validation (Isaac) |
|--------|---------------------|---------------------|
| Goal | Max episode throughput | Real geometry + contact |
| Physics | Differentiable CUDA | PhysX rigid body |
| Arena | Simplified / curriculum | Full RM STL |
| Depth | Differentiable renderer | Real camera sensor |
| Purpose | Learn the policy | Independently verify it |

Using two simulators forces the policy to be robust rather than overfitting one physics engine.

## Policy Architecture

```
Depth (320x240x1) ──► CNN (3 conv layers) ──► 128-d visual feature
                                                        │
State vector (12-d) ──► MLP ──► 64-d state feature      │
                              (rel_goal 3 + vel 3       │
                               + gravity 3 + ang_vel 3) │
                                                        │
[visual, state] concat (192-d) ──► GRU (hidden=128) ──► MLP ──► action (4-d)
```

Action: `[ax, ay, az, yaw_rate]` — high-level, matches DiffPhys original definition.

## Mission State Machine (not AI)

```
TAKEOFF ──► ATTACK ──► HIT ──► RECOVER ──► RETURN ──► HOME
              │                                    ▲
              └── goal = ArmorTarget               └── goal = HOME
```

The same policy handles goal-directed flight in both ATTACK and RETURN.
HIT detection = contact with independent ArmorTarget collider.

## Collision Classification

| Contact | Classification |
|---------|---------------|
| Drone ↔ ArmorTarget | **TARGET_HIT** (SUCCESS) |
| Drone ↔ Arena (any other) | **WRONG_COLLISION** (FAILURE) |
| No contact, time expired | TIMEOUT |

ArmorTarget is NEVER included in obstacle-avoidance loss.

## Coordinate Frames

- **world**: FLU, z-up, origin at arena center
- **body**: FLU, z-up, origin at drone CG
- **camera**: FLU, z-up, origin at camera mount, forward = +x

All transforms are explicit in config; no "tune until it works" coordinate hacks.
