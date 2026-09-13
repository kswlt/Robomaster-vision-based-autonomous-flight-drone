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
| Isaac Sim scene code | 🔶 Written | sim/isaac/*.py — cannot run (Isaac not installed) |
| Scripted baseline | 🔶 Written | controller.py + episode.py — untested (needs Isaac) |
| Headless eval | 🔶 Written | evaluate.py + run_eval.ps1 — untested (needs Isaac) |
| DiffPhys upstream | ⏳ Pending | Clone + reproduce in WSL2 |
| RK3588 export | ⏳ Pending | After policy training |

## Verified

- STL loads in trimesh, geometry analyzed, unit calibrated to meters
- Arena reference images confirm 28m×15m official battlefield
- Armor bracket dimensions extracted from engineering drawing
- WSL2 GPU access confirmed (nvidia-smi works inside Ubuntu)
- GitHub remote accessible via Clash proxy (repo-local config)
- Python 3.14 + numpy 2.5.2 + trimesh 5.1.0 + matplotlib 3.11.2 on Windows

## Current Blockers

1. **Isaac Sim not installed** — disk space insufficient (C: 30.9GB free, need ~40GB for 9.66GB download + ~30GB extraction). sim/isaac code is written but cannot be executed. All Isaac-dependent milestones (1, 4) blocked until disk freed or install moved to another drive.
2. **Armor module exact dimensions** — not in provided images; using placeholder 0.135×0.055m. Need official RMUC 2026 armor module spec.
3. **Armor plate normal/orientation** — defaulted to face -x; needs STL face normal analysis or user confirmation.

## Next Steps

1. ✅ Push clean skeleton to origin/E2E-RL (force-with-lease)
2. Clone DiffPhysDrone in WSL2, pin commit, reproduce original training (milestone 2)
3. Modify DiffPhys objective for target-impact (milestone 3)
4. When disk space available: install Isaac Sim 6.1.0, run scripted baseline 20 episodes (milestone 1)
5. Checkpoint → Isaac validation (milestone 4)
