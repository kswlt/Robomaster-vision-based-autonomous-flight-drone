# Current State

**Last updated**: 2026-09-14 (JST)
**Branch**: E2E-RL (orphan rebuild)

## Completion

| Area | Status | Details |
|------|--------|---------|
| Git rebuild | ✅ Done | Orphan E2E-RL, remote fetched, proxy configured |
| Input asset backup | ✅ Done | C:\RM_E2E_INPUT_BACKUP\, SHA256 recorded |
| Environment audit | ✅ Done | docs/ENVIRONMENT.md |
| STL analysis | ✅ Done | Unit=meters, 28×15m, 124995 tris, artifact at z=18 |
| Armor image analysis | ✅ Done | Bracket 135×38mm, rigidity 60N/2.5°, plate dims TODO |
| Project skeleton | ✅ Done | configs/, docs/, sim/, training/, deployment/, scripts/, tests/ |
| Configs | ✅ Done | 7 YAML files with real data |
| Isaac Sim install | ✅ Done | 6.1.0 standalone at C:\isaacsim, post_install complete |
| Isaac Sim scene code | ✅ Done | sim/isaac/*.py — updated for Isaac 6.1.0 API, executed in real Isaac |
| Scripted baseline | ✅ Done | controller.py + episode.py — **real Isaac 20ep 100% hit** |
| Headless eval | ✅ Done | evaluate.py + run_eval.ps1 — **real Isaac 20ep 100% hit**, JSON+CSV output |
| DiffPhys env build | ✅ Done | WSL2: PyTorch 2.2.2+cu118, CUDA 11.8, quadsim_cuda built & verified |
| DiffPhys upstream training | ✅ Done | 3000 iters: loss 27.3→3.3; checkpoint save/load verified (514K params) |
| Target-impact training | ✅ Done | 6000 iters, 1000ep eval: **80.5% hit rate**, impact_vel 0.8m/s, angle 41.9° |
| Isaac real physics eval | ✅ Done | **Milestone 1: 20/20 hit, 100% rate, 0 wrong, 0 timeout** |
| Checkpoint→Isaac eval | 🔶 In Progress | **100ep: 100% hit, impact angle 23.6°, vel 0.84m/s**; 1000ep running |
| RK3588 export | ⏳ Pending | After 1000ep validation |

## Verified

- STL loads in trimesh, geometry analyzed, unit calibrated to meters
- Arena reference images confirm 28m×15m official battlefield
- Armor bracket dimensions extracted from engineering drawing
- WSL2 GPU access confirmed (nvidia-smi works inside Ubuntu)
- GitHub remote accessible via Clash proxy (repo-local config)
- Python 3.14 + numpy 2.5.2 + trimesh 5.1.0 + matplotlib 3.11.2 on Windows
- **quadsim_cuda extension built and importable**: all 6 functions verified
- **DiffPhys training starts and loss decreases**: 27.3→3.3 in 3000 iters
- **Checkpoint save/load verified**: checkpoint0003.pth (3000 iters), 514,496 params, CPU+GPU forward pass OK
- **Target-impact training complete**: 6000 iters, 1000ep eval: **80.5% hit rate**, impact_vel 0.8m/s, angle 41.9°
- **Isaac Sim 6.1.0 installed**: standalone ZIP at C:\isaacsim, post_install done
- **Isaac Sim 6.1.0 Python env verified**: isaacsim.SimulationApp, isaacsim.core.api.world.World, isaacsim.core.api.objects, warp 1.16.0 CUDA
- **Kinematic fallback eval**: 20 episodes, 100% hit rate, full metrics pipeline
- **Milestone 1 — Real Isaac scripted baseline**: 20/20 episodes hit=True, 100% target_hit_rate, 0 wrong_collisions, 0 timeouts, impact_velocity_mean=1.18 m/s

## Current Blockers

1. **Armor module exact dimensions** — placeholder 0.135×0.055m. Need official RMUC 2026 spec.
2. **Armor plate normal/orientation** — defaulted to face -x; needs STL face normal analysis.
3. **Impact velocity low (0.8 m/s in DiffPhys, 1.18 in Isaac)** — policy approaches slowly. More training or higher speed_mtp may improve.
4. **Impact angle 155° in Isaac** — angle calculation may have sign/frame bug. Need to verify.
5. **Checkpoint→Isaac not yet validated** — policy_wrapper.py written but not run with real checkpoint.

## Next Steps

1. ~~Test Isaac Sim Python environment~~ ✅ Done
2. ~~Run scripted baseline in real Isaac Headless (milestone 1)~~ ✅ Done
3. Import target-impact checkpoint into Isaac, run 1000 episodes (milestone 4)
4. Fix impact angle calculation bug
5. Add depth noise/domain randomization, re-evaluate (milestone 5)
6. Export ONNX/RKNN for RK3588 (milestone 5)
