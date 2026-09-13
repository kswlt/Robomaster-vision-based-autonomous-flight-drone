# Isaac Sim

## Version
Isaac Sim 6.1.0 standalone (Windows x86_64). Omniverse Launcher deprecated 2025-10-01.

## Installation (when disk space available)
```powershell
mkdir C:\isaacsim
cd $env:USERPROFILE\Downloads
tar -xvzf isaac-sim-standalone-6.1.0-windows-x86_64.zip -C C:\isaacsim
cd C:\isaacsim
.\post_install.bat
```
Download: https://downloads.isaacsim.nvidia.com/isaac-sim-standalone-6.1.0-windows-x86_64.zip (9.66 GB)

## Scene Layout
```
/World
├── Arena          (RMUC 2026 STL, visual + simplified collision)
├── ArmorTarget    (independent box collider, NOT part of arena)
├── Drone          (simplified rigid body, sphere collider)
└── Sensors
    └── DepthCamera (front-facing, 320x240, 90deg FOV)
```

## Key Scripts
- `sim/isaac/build_scene.py` — assemble the world
- `sim/isaac/arena.py` — STL import, z-clip, collision simplification
- `sim/isaac/armor_target.py` — independent collider + contact reporting
- `sim/isaac/drone.py` — rigid body, reset/step/get_state interface
- `sim/isaac/depth_camera.py` — ideal depth, PNG/NPY export
- `sim/isaac/controller.py` — scripted PD baseline (phase 1)
- `sim/isaac/episode.py` — mission state machine, reset, metrics
- `sim/isaac/evaluate.py` — headless N-episode evaluation

## Running
```powershell
# GUI (debug only)
powershell -File scripts/run_isaac_gui.ps1

# Headless evaluation
powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 20
```

## Contact Classification
- Drone ↔ ArmorTarget → TARGET_HIT
- Drone ↔ Arena → WRONG_COLLISION
- ArmorTarget is in its own collision group.

## Current Status
Code written, **not executed** (Isaac not installed due to disk space). See docs/KNOWN_ISSUES.md.
