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

- [x] Clone repo, pin commit SHA → `training/diffphys/upstream_commit.txt` (commit 2719361)
- [x] Install PyTorch 2.2.2+cu118 in WSL2 Python 3.10 venv
- [x] Install CUDA Toolkit 11.8 (nvcc V11.8.89)
- [x] Build custom CUDA extension `quadsim_cuda` (10.3MB .so)
- [x] Run `main_cuda.py` with single_agent config (3000 iters, in progress)
- [ ] Verify: loss decreases over iterations (observed: 27→6 in 200 iters)
- [ ] Verify: checkpoint saved to expected path
- [ ] Verify: checkpoint can be reloaded (load_state_dict)
- [ ] Verify: validation run produces metrics
- [x] Record: upstream commit SHA, patches, environment

## Build Notes (Critical)

The CUDA extension build has several pitfalls on WSL2:

1. **NumPy version**: Must use `numpy<2` (1.26.4 tested). NumPy 2.x causes `_ARRAY_API not found` when importing torch 2.2.2.
2. **pip build isolation**: `pip install -e .` fails with `ModuleNotFoundError: No module named 'torch'` because the isolated build env doesn't have torch. Use `--no-build-isolation`.
3. **PEP 660 editable**: Old setuptools in setup.py doesn't support editable installs. Use non-editable `pip install .` or direct `python setup.py build_ext --inplace`.
4. **WSL2 /mnt/c filesystem**: Compilation on /mnt/c is extremely slow (>15min, may hang). Copy source to WSL native filesystem (`~/diffphys_build/`) and build there, then copy .so back.
5. **WSL memory**: Need >8GB free RAM. `wsl --shutdown` if `Cannot allocate memory`.

Working build command sequence:
```bash
# In WSL, with venv activated and CUDA 11.8 on PATH
pip install "numpy<2" wheel ninja
cp upstream/src/* ~/diffphys_build/
cd ~/diffphys_build
python setup.py build_ext --inplace
cp quadsim_cuda*.so $(python -c "import site; print(site.getsitepackages()[0])")/
```

## Environment
- WSL2 Ubuntu 22.04, Python 3.10.12
- PyTorch 2.2.2+cu118, CUDA available (RTX 4060 Laptop 8GB)
- CUDA Toolkit 11.8 (nvcc V11.8.89)
- NumPy 1.26.4
- quadsim_cuda functions: render, run_forward, run_backward, find_nearest_pt, update_state_vec, rerender_backward

## Model Architecture (Confirmed from source)
- Input: depth (1,1,12,16) after 4x maxpool from 64x48 + state vector (10-dim)
- CNN: Conv(1→32, k2 s2) → Conv(32→64, k3) → Conv(64→128, k3) → Flatten(1024) → Linear(192)
- State proj: Linear(10→192)
- GRUCell(192, 192)
- Output: Linear(192→6) = thrust vector (3) + velocity prediction (3)
- State vector (no_odom=False): 7 base + 3 odom velocity = 10
- forward(depth, state, hx) → (action, None, new_hx)

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
- Upstream cloned at commit 2719361, code fully read and understood
- WSL2 environment ready: PyTorch 2.2.2+cu118, CUDA 11.8, quadsim_cuda built and verified
- Original training running: 3000 iters, batch=64, single_agent config
- Loss observed decreasing: 27.3 (iter 0) → ~6.0 (iter 200)
- Training speed: ~2 it/s on RTX 4060 Laptop
- Next: verify checkpoint save/load, then modify for target-impact objective
