# Handoff

Read this file to continue the project from where it left off.

## Quick Context

This is a complete rebuild of the E2E-RL branch. Legacy ROS2/VIO/Jetson/PX4 is discarded. Final platform is RK3588. Training = DiffPhysDrone in WSL2. Validation = Isaac Sim on Windows.

## Where Things Are

- **Repo root**: `C:\Users\Admin\Desktop\端到端强化学习无人机仿真\`
- **Branch**: `E2E-RL` (orphan, clean history)
- **Remote**: `origin` → https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone
- **Git proxy**: repo-local `http.proxy=http://127.0.0.1:7890` (Clash must be running)
- **Input backup**: `C:\RM_E2E_INPUT_BACKUP\` (STL + armor images, SHA256 in docs/ASSETS.md)

## What's Done

1. Git orphan rebuild, all old code removed
2. Environment audited (docs/ENVIRONMENT.md)
3. STL analyzed: unit=meters, 28×15m arena, 124995 triangles (docs/ASSETS.md)
4. Armor images analyzed: bracket 135×38mm (docs/ASSETS.md)
5. Full project skeleton + 7 configs + docs written
6. sim/isaac code written (arena, armor_target, drone, depth_camera, controller, episode, evaluate)
7. scripts/ written (check_environment, setup, run_eval, run_diffphys_wsl, export_rk3588)

## What's Blocked

### Isaac Sim (CRITICAL for milestones 1 & 4)
- NOT installed. Download is 9.66GB, extracts to ~30GB+.
- C: has 30.9GB free, E: has 15.4GB free — neither fits the full install.
- **To unblock**: Free at least 40GB on C: (or another NTFS drive), then:
  ```powershell
  mkdir C:\isaacsim
  tar -xvzf isaac-sim-standalone-6.1.0-windows-x86_64.zip -C C:\isaacsim
  cd C:\isaacsim; .\post_install.bat
  ```
- Download URL: https://downloads.isaacsim.nvidia.com/isaac-sim-standalone-6.1.0-windows-x86_64.zip
- Official guide: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/quick-install.html

### Armor module dimensions
- Placeholder 0.135×0.055m in configs/armor.yaml. Verify against official RMUC 2026 robot specification manual.

## Immediate Next Action

**Clone DiffPhysDrone in WSL2 and reproduce original training** (milestone 2). This does NOT require Isaac Sim and is the highest-priority unblocked work.

```powershell
wsl -e bash -lc "
  cd /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys
  git clone https://github.com/HenryHuYu/DiffPhysDrone upstream
  cd upstream && git rev-parse HEAD > ../upstream_commit.txt
"
```

Then install PyTorch (CUDA) + build the CUDA extension in WSL2, run main_cuda.py, verify loss updates and checkpoint saves. See docs/DIFFPHYS.md for the checklist.

## Key Files to Read First

1. `docs/CURRENT_STATE.md` — live status
2. `docs/ARCHITECTURE.md` — system design
3. `docs/DECISIONS.md` — why things are this way
4. `configs/arena.yaml` — arena geometry (unit=meters)
5. `configs/armor.yaml` — target definition
6. `configs/training.yaml` — DiffPhys policy + objective

## Commit & Push Rules

- Every stage completion → `git add -A && git commit && git push`
- First push used `--force-with-lease`; subsequent pushes are normal
- NEVER force-push main, master, or d430
- Commit messages follow the recommended list in the task spec
