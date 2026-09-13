# Experiment Log

Format: date | commit | config | checkpoint | episodes | metrics | conclusion

---

## 2026-09-14 — Environment & Asset Audit

- **Commit**: (initial skeleton, pending push)
- **Config**: N/A (audit phase)
- **Checkpoint**: N/A
- **Episodes**: 0
- **Metrics**:
  - STL: 124,995 triangles, extents 29.15×16.05×18.04 raw
  - Unit calibrated: meters (official 28×15m battlefield)
  - Stray artifact: 8 vertices at z≈18
  - Armor bracket: 135×38mm, diag 125mm
  - WSL2 GPU: RTX 4060 Laptop, 8GB, driver 591.86
- **Conclusion**: Environment ready for DiffPhys training in WSL2. Isaac Sim blocked by disk space (30.9GB free, need ~40GB). Asset geometry fully analyzed.

---

## 2026-09-14 — DiffPhys Upstream Reproduction (Milestone 2)

- **Commit**: 361a518
- **Config**: single_agent.args (batch=64, lr=1e-3, ctl_dt=1/15, timesteps=150, ground_voxels, random_rotation, yaw_drift, coef_collide=7.5, coef_obj_avoidance=3.0, speed_mtp=4, cam_angle=20, fov_x_half_tan=0.82)
- **Checkpoint**: upstream saves every 10000 iters; modified version (main_upstream_ckpt.py) saves every 1000 iters. 10000-iter run in progress.
- **Episodes**: 3000 training iterations × 64 batch = 192,000 episodes
- **Metrics**:
  - Loss trajectory: 27.25 (iter 0) → 9.4 (iter 50) → 5.8 (iter 200) → 3.5 (iter 1000) → 3.3 (iter 3000)
  - Training speed: ~2.5 it/s on RTX 4060 Laptop 8GB
  - Total time: 19m34s for 3000 iters
  - CUDA extension: quadsim_cuda built and verified (6 functions: render, run_forward, run_backward, find_nearest_pt, update_state_vec, rerender_backward)
- **Environment**: WSL2 Ubuntu 22.04, Python 3.10.12, PyTorch 2.2.2+cu118, CUDA Toolkit 11.8 (nvcc V11.8.89), NumPy 1.26.4
- **Build notes**: quadsim_cuda must be built on WSL native filesystem (not /mnt/c) due to I/O speed; use `python setup.py build_ext --inplace` with `numpy<2` and `--no-build-isolation` if using pip.
- **Conclusion**: DiffPhys upstream training successfully reproduced. Loss decreases steadily. 10000-iter run in progress to obtain checkpoint for save/load verification. Next: target-impact training (milestone 3).

---

## 2026-09-14 — Isaac Sim Installation

- **Commit**: 949f155
- **Config**: Isaac Sim 6.1.0 standalone (Windows)
- **Checkpoint**: N/A
- **Episodes**: 0
- **Metrics**:
  - Install path: C:\isaacsim\
  - Installer: isaac-sim-standalone-6.1.0-windows-x86_64.zip (9.66GB)
  - post_install.bat: completed (symlink extension_examples)
  - Disk space after install: ~228GB free (user cleaned disk)
- **Conclusion**: Isaac Sim 6.1.0 installed and ready. Next: test Python environment, load RM STL arena, run scripted baseline (milestone 1).

---

## (Template for future entries)

## YYYY-MM-DD — Experiment Name

- **Commit**: `<sha>`
- **Config**: `<config file / key params>`
- **Checkpoint**: `<path>`
- **Episodes**: `<N>`
- **Metrics**:
  - target_hit_rate: `<value>`
  - wrong_collision_rate: `<value>`
  - ...
- **Conclusion**: `<what worked, what didn't, next step>`
