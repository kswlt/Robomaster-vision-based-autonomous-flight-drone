# Handoff

Read this file to continue the project from where it left off.

## Quick Context

Complete rebuild of E2E-RL branch. Legacy ROS2/VIO/Jetson/PX4 discarded. Final platform RK3588. Training = DiffPhysDrone in WSL2/CUDA. Validation = Isaac Sim 6.1.0 on Windows.

## Where Things Are

- **Repo root**: `C:\Users\Admin\Desktop\端到端强化学习无人机仿真\`
- **Branch**: `E2E-RL` (orphan, clean history) @ commit 81b0564
- **Remote**: `origin` → https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone
- **Git proxy**: repo-local `http.proxy=http://127.0.0.1:7890` (Clash must be running on 7890)
- **Input backup**: `C:\RM_E2E_INPUT_BACKUP\` (STL + armor images, SHA256 in docs/ASSETS.md)
- **Isaac Sim**: `C:\isaacsim\` (6.1.0 standalone, installed)
- **DiffPhys upstream**: `training/diffphys/upstream/` (commit 2719361, in .gitignore)
- **WSL venv**: `training/diffphys/venv/` (PyTorch 2.2.2+cu118, numpy 1.26.4, quadsim_cuda built)

## What's Done

1. Git orphan rebuild, all old code removed, force-pushed to origin/E2E-RL
2. Environment audited (docs/ENVIRONMENT.md)
3. STL analyzed: unit=meters, 28×15m arena, 124,995 triangles (docs/ASSETS.md)
4. Armor images analyzed: bracket 135×38mm (docs/ASSETS.md)
5. Full project skeleton + 7 configs + 13 docs
6. sim/isaac code written (arena, armor_target, drone, depth_camera, controller, episode, evaluate, policy_wrapper)
7. Kinematic fallback eval tested: 20 episodes, 100% hit rate, full metrics pipeline (results/eval_results.json)
8. 35 unit tests pass (tests/)
9. **Isaac Sim 6.1.0 installed** at C:\isaacsim, post_install complete
10. **DiffPhys WSL2 environment ready**: PyTorch 2.2.2+cu118, CUDA 11.8, quadsim_cuda built & verified
11. **DiffPhys upstream training verified**: 3000 iters, loss 27.3→3.3, ~2.5 it/s on RTX 4060
12. **10000-iter upstream training running** (for checkpoint save/load verification)
13. Target-impact training script written (train_target_impact.py): 7 loss terms, curriculum, checkpoint every 2000 iters
14. **Milestone 1 complete**: Real Isaac 20ep 100% hit rate
15. **Milestone 2 complete**: DiffPhys upstream 10000 iters, checkpoint verified
16. **Milestone 3 complete**: Target-impact 6000 iters, 1000ep 80.5% hit
17. **Milestone 4 complete**: Checkpoint→Isaac 1000ep **100% hit**, impact angle 23.6°
18. **Milestone 5 complete**: Sim-to-Real noise 100% hit across all levels; ONNX 35.9KB exported & validated
19. **RK3588 ONNX ready**: deployment/onnx/policy.onnx, ORT inference diff 9.5e-07

## Milestone Status

| Milestone | Status | Details |
|-----------|--------|---------|
| M1: Isaac scripted baseline 20ep | ✅ Done | 20/20 hit, 100% rate, 0 wrong, 0 timeout |
| M2: DiffPhys upstream reproduction | ✅ Done | 10000 iters, loss 27.3→3.3, checkpoint save/load verified |
| M3: Target-impact training 1000ep | ✅ Done | 6000 iters, 80.5% hit rate in DiffPhys env |
| M4: Checkpoint → Isaac 1000ep | ✅ Done | **1000/1000 hit (100%)**, impact angle 23.6°, vel 0.84m/s |
| M5: Noise + RK3588 export | ✅ Done | 100% hit across all noise levels; ONNX 35.9KB validated |

## WSL2 Quick Commands

```powershell
# Activate venv and run upstream training (10000 iters, checkpoint every 1000)
wsl -e bash /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/scripts/wsl_run_upstream_10k.sh 10000

# Run target-impact training
wsl -e bash -c "
  source /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys/venv/bin/activate
  export PATH=/usr/local/cuda-11.8/bin:\$PATH
  cd /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys
  python target_env/train_target_impact.py --num_iters 10000 --batch_size 64
"

# Verify quadsim_cuda
wsl -e bash -c "
  source /mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真/training/diffphys/venv/bin/activate
  python -c 'import quadsim_cuda; print(dir(quadsim_cuda))'
"
```

## WSL Proxy (critical for network)

WSL2 cannot reach 127.0.0.1:7890 (that's Windows localhost). Use Windows host IP:
```bash
export http_proxy=http://172.22.0.1:7890
export https_proxy=http://172.22.0.1:7890
```

## Isaac Sim Quick Commands

```powershell
# Run Python in Isaac env
C:\isaacsim\python.bat -c "print('Isaac Python OK')"

# Run headless eval (after Isaac code is verified)
powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 20
```

## Critical Build Notes (quadsim_cuda)

1. Must use `numpy<2` (1.26.4 tested). NumPy 2.x breaks torch 2.2.2 import.
2. Build on WSL native filesystem (`~/diffphys_build/`), NOT /mnt/c (too slow, may hang).
3. Use `python setup.py build_ext --inplace` (not pip editable - old setuptools lacks PEP 660).
4. Copy resulting .so to venv site-packages.
5. Need >8GB WSL RAM. `wsl --shutdown` if `Cannot allocate memory`.

## What's Blocked / Open Items

1. **Armor module exact dimensions** — placeholder 0.135×0.055m in configs/armor.yaml. Need official RMUC 2026 spec.
2. **Armor plate normal/orientation** — defaulted to face -x; needs STL face normal analysis.
3. **Impact velocity low (0.84 m/s)** — target range 2-10 m/s. Needs more training or higher speed_mtp.
4. **Real Isaac depth camera** — currently using synthetic depth. Need to integrate isaacsim.sensors.camera.Camera.
5. **RKNN conversion** — ONNX ready, needs RKNN Toolkit2 + RK3588 hardware for benchmark.
6. **Impact recovery & return HOME** — episode ends on HIT (phase 1). Phase 2 needs recovery + return flight.
7. **Arena STL visual** — using simplified box colliders. STL visual loading optional/untested.

## Immediate Next Actions

1. **Integrate real Isaac depth camera**: Replace synthetic depth with isaacsim.sensors.camera.Camera.
2. **Increase impact velocity**: Train with higher speed_mtp or velocity reward shaping, target 2-10 m/s.
3. **RKNN Toolkit2 conversion**: Convert policy.onnx → policy.rknn, test FP16/INT8 quantization.
4. **Impact recovery (phase 2)**: Post-impact attitude recovery and return-to-HOME controller.
5. **Domain randomization training**: Retrain with depth noise/latency/mass variation for heavy-noise robustness.
6. **1000ep with real depth**: Full evaluation with real Isaac depth camera, compare to synthetic results.

## Key Files to Read First

1. `docs/CURRENT_STATE.md` — live status
2. `docs/DIFFPHYS.md` — upstream reproduction details, build notes, model architecture
3. `docs/ARCHITECTURE.md` — system design
4. `docs/DECISIONS.md` — why things are this way
5. `configs/arena.yaml` — arena geometry (unit=meters)
6. `configs/armor.yaml` — target definition
7. `configs/training.yaml` — DiffPhys policy + objective
8. `training/diffphys/target_env/train_target_impact.py` — target-impact training
9. `sim/isaac/evaluate.py` — Isaac evaluation + kinematic fallback

## Commit & Push Rules

- Every stage completion → `git add -A && git commit && git push`
- First push used `--force-with-lease`; subsequent pushes are normal
- NEVER force-push main, master, or d430
- upstream/ directory is in .gitignore (contains its own .git)
- venv/ directory is in .gitignore
