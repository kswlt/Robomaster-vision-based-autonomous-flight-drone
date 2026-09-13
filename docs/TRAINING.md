# Training

See configs/training.yaml for all parameters.

## Pipeline
1. DiffPhysDrone CUDA environment (WSL2, GPU)
2. CNN+GRU+MLP policy (small, RK3588-friendly)
3. Target-impact objective (NOT obstacle avoidance)
4. 6-stage curriculum
5. Checkpoint → ONNX export

## Objective
```
L = w_goal * L_goal
  + w_hit  * L_target_hit
  + w_wrong * L_wrong_collision   (negative, large penalty)
  + w_center * L_center_hit
  + w_angle * L_impact_angle
  + w_vel * L_impact_velocity
  + w_ctrl * L_control
  + w_time * L_time
```
ArmorTarget is NEVER in the avoidance term.

## Curriculum
1. No obstacles, fixed HOME/target
2. Random initial position/yaw
3. Add non-target obstacles
4. Mass/velocity/delay randomization
5. Full RM STL arena
6. Depth domain randomization

## Running
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_diffphys_wsl.ps1
```

## Current Status
Pending. DiffPhys upstream not yet cloned.
