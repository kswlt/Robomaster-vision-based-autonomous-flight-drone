# Decisions

## Why Depth (not RGB)

- Depth is a unified perception interface: same format from Isaac Sim ideal depth and real depth camera.
- Depth normalizes lighting/color domain gap — critical for sim-to-real.
- DiffPhysDrone (the core reference) uses depth as primary visual input.
- RGB would add unnecessary domain randomization burden and larger model size, conflicting with RK3588 constraints.

## Why Training and Isaac Are Separated

- DiffPhys CUDA environment provides differentiable physics → orders of magnitude higher episode throughput than Isaac.
- Isaac Sim provides independent validation with real STL geometry, PhysX contact, and camera sensor model.
- Using two simulators detects sim-to-sim gaps early; a policy that only works in DiffPhys is not deployable.
- Training fully dependent on Isaac would be too slow and non-differentiable.

## Why RK3588 (not Jetson Orin NX)

- Final competition platform is explicitly RK3588.
- RK3588 has 3-core NPU suitable for small CNN + MLP; GRU can fall back to ARM CPU if needed.
- Policy designed small from day one (CNN+GRU+MLP, no Transformer/attention) to fit RKNN.
- Jetson/NX toolchain and all legacy code discarded.

## Why Not RGB→PWM

- End-to-end RGB→PWM is unstable, hard to debug, and impossible to safely transfer to real hardware.
- High-level action (acceleration + yaw rate) matches DiffPhys original and interfaces cleanly with any flight controller.
- Flight controller handles attitude stabilization and motor output; RK3588 only does perception + policy.
- Separation of concerns makes sim-to-real transfer tractable.

## Why Target Collision Is Success

- The task is defined as "actively impact the designated enemy armor plate."
- Hitting the armor plate = SUCCESS; hitting any other structure = FAILURE.
- This is the opposite of standard obstacle-avoidance RL — the objective explicitly rewards collision with the target.
- ArmorTarget is an independent collider so contact classification is unambiguous.

## Why Isaac Is the Independent Validator

- Isaac Sim uses PhysX (different physics from DiffPhys CUDA), real RM STL mesh, and a proper depth camera sensor.
- Headless automated evaluation gives reproducible metrics across 1000+ episodes.
- If policy performance drops from DiffPhys to Isaac, the gap is localized and fixable before hardware.
- Isaac is NOT used for training — only for verification.

## Why Orphan Branch Rebuild

- Legacy E2E-RL contained ROS2/VIO/Jetson/PX4 architecture incompatible with the new RK3588 + DiffPhys direction.
- `git checkout --orphan E2E-RL` creates a clean history with no inherited files.
- `--force-with-lease` (not bare `--force`) protects against overwriting unexpected remote changes.
- main, master, d430 branches are never modified.

## Why Repo-Local Git Proxy

- Clash listens on 127.0.0.1:7890; direct git to GitHub fails while web requests succeed (WinINET proxy).
- `git config http.proxy` is set in repo scope only, not global Windows settings.
- Easily removable: `git config --unset http.proxy` in this repo.
