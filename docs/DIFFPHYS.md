# DiffPhysDrone Upstream Reproduction

## Reference
- Repo: https://github.com/HenryHuYu/DiffPhysDrone
- Paper: "Learning vision-based agile flight via differentiable physics", Nature Machine Intelligence, 2025
- Location in repo: `training/diffphys/upstream/`

## Must Read Before Modifying
- README.md
- main_cuda.py
- model.py
- env_cuda.py
- CUDA extension files (*.cu, *.cpp)
- Training config / loss / observation / action / validation

## Reproduction Checklist (WSL2)

- [ ] Clone repo, pin commit SHA → `training/diffphys/upstream_commit.txt`
- [ ] Install PyTorch (CUDA) in WSL2 Python 3.10 venv
- [ ] Build custom CUDA extension (`python setup.py install` or equivalent)
- [ ] Run `main_cuda.py` with default config
- [ ] Verify: loss decreases over iterations
- [ ] Verify: checkpoint saved to expected path
- [ ] Verify: checkpoint can be reloaded (load_state_dict)
- [ ] Verify: validation run produces metrics
- [ ] Record: upstream commit SHA, any patches applied, environment

## Key Things to Understand
- Depth input preprocessing (resolution, normalization, crop/pool)
- CNN architecture + GRU hidden state handling
- State vector composition (relative goal, velocity, attitude/gravity)
- Action definition (acceleration? velocity? thrust? yaw rate?)
- dt and dynamics integration
- Collision loss and avoidance loss (we will REPLACE avoidance with target-hit)
- Checkpoint format and validation protocol

## Modification Plan
1. Reproduce original as-is (no changes)
2. Add target-impact objective (L_target_hit, L_wrong_collision, L_center_hit, L_impact_angle, L_impact_velocity)
3. Remove ArmorTarget from obstacle avoidance loss
4. Add curriculum stages (see configs/training.yaml)
5. Validate in 1000 randomized episodes

## Current Status
Pending. Not yet cloned. See docs/CURRENT_STATE.md.
