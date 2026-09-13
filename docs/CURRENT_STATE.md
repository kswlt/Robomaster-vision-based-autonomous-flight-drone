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
| Isaac Sim scene code | 🔶 Written | sim/isaac/*.py — not yet executed in real Isaac |
| Scripted baseline | 🔶 Written | controller.py + episode.py — kinematic fallback tested, real Isaac pending |
| Headless eval | 🔶 Written | evaluate.py + run_eval.ps1 — kinematic fallback 20ep 100% hit, real Isaac pending |
| DiffPhys env build | ✅ Done | WSL2: PyTorch 2.2.2+cu118, CUDA 11.8, quadsim_cuda built & verified |
| DiffPhys upstream training | 🔄 Running | 3000 iters, loss 27→6 in 200 iters, ~2 it/s |
| Target-impact training | ⏳ Pending | Code written, after upstream repro verified |
| RK3588 export | ⏳ Pending | After policy training |

## Verified

- STL loads in trimesh, geometry analyzed, unit calibrated to meters
- Arena reference images confirm 28m×15m official battlefield
- Armor bracket dimensions extracted from engineering drawing
- WSL2 GPU access confirmed (nvidia-smi works inside Ubuntu)
- GitHub remote accessible via Clash proxy (repo-local config)
- Python 3.14 + numpy 2.5.2 + trimesh 5.1.0 + matplotlib 3.11.2 on Windows
- **quadsim_cuda extension built and importable**: all 6 functions verified
- **DiffPhys training starts and loss decreases**: 27.3→6.0 in 200 iters
- **Isaac Sim 6.1.0 installed**: standalone ZIP at C:\isaacsim, post_install done
- **Kinematic fallback eval**: 20 episodes, 100% hit rate, full metrics pipeline

## Current Blockers

1. **Armor module exact dimensions** — not in provided images; using placeholder 0.135×0.055m. Need official RMUC 2026 armor module spec.
2. **Armor plate normal/orientation** — defaulted to face -x; needs STL face normal analysis or user confirmation.
3. **Real Isaac Sim execution not yet done** — Isaac installed but sim/isaac code not yet run against real Isaac Python env. Need to verify Isaac Python API compatibility (6.1.0 uses newer omni.isaac.* API).

## Next Steps

1. 🔄 Wait for DiffPhys upstream 3000-iter training to complete, verify checkpoint save/load
2. Run target-impact training (train_target_impact.py) in WSL2 (milestone 3)
3. Test Isaac Sim Python environment: run simple scene load with real STL
4. Run scripted baseline in real Isaac Headless (milestone 1)
5. Checkpoint → Isaac validation (milestone 4)
