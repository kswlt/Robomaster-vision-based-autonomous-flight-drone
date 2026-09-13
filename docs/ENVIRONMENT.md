# Environment Audit

Generated: 2026-09-14 (JST)
Script: `scripts/check_environment.ps1` (reproducible)

## Host System

| Item | Value |
|------|-------|
| OS | Windows 11 Pro Workstation 10.0.26200 |
| RAM | 21.7 GB |
| Disk C: | 30.9 GB free / 1502 GB total |
| Disk E: | 15.4 GB free / 954 GB total |

## GPU

| Item | Value |
|------|-------|
| GPU | NVIDIA GeForce RTX 4060 Laptop |
| VRAM | 8 GB |
| Driver | 591.86 |
| CUDA (driver support) | 13.1 |
| CUDA toolkit (nvcc) | 11.8 (V11.8.89) |

## Development Tools

| Item | Value |
|------|-------|
| Python (default) | 3.14.7 |
| Python (available) | 3.14, 3.13, 3.11 (Store), Anaconda 3.9 |
| Git | 2.52.0.windows.1 |
| CMake | 3.31.5 |
| Visual Studio Build Tools | Not detected (vswhere empty) |
| WSL2 | Ubuntu (running, v2) |
| Docker | 29.2.0 (docker-desktop running) |

## WSL2 (Ubuntu)

| Item | Value |
|------|-------|
| Distro | Ubuntu |
| Python | 3.10.12 |
| GLIBC | 2.35 |
| GPU access | Yes (nvidia-smi works, driver 591.86) |
| PyTorch | Not installed yet |

## Isaac Sim

| Item | Value |
|------|-------|
| Installed | **No** |
| Target version | 6.1.0 (standalone ZIP) |
| Download URL | https://downloads.isaacsim.nvidia.com/isaac-sim-standalone-6.1.0-windows-x86_64.zip |
| Download size | 9.66 GB |
| Estimated extracted size | ~30+ GB |
| **Blocker** | **Insufficient disk space** (C: 30.9 GB free, E: 15.4 GB free) |

### Isaac Sim Installation Notes

- Omniverse Launcher deprecated as of 2025-10-01. Use standalone ZIP.
- Install steps: `mkdir C:\isaacsim`, `tar -xvzf isaac-sim-standalone-6.1.0-windows-x86_64.zip -C C:\isaacsim`, `post_install.bat`, `isaac-sim.bat`.
- Official docs: https://docs.isaacsim.omniverse.nvidia.com/latest/installation/quick-install.html
- **Action required**: Free at least 40 GB on C: (or another drive) before installing Isaac Sim. Until then, sim/isaac code is written but cannot be executed.

## Network

| Item | Value |
|------|-------|
| Direct GitHub (HTTPS) | Web works, git fails (needs proxy) |
| Clash proxy | 127.0.0.1:7890 (listening) |
| Git proxy config | Repo-local: http.proxy=http://127.0.0.1:7890 |
| WSL2 proxy | Uses Windows host gateway (172.22.0.1:7890) |

## Git

| Item | Value |
|------|-------|
| Remote | https://github.com/kswlt/Robomaster-vision-based-autonomous-flight-drone |
| Current branch | E2E-RL (orphan, rebuilt) |
| Protected branches | main, master, d430 (never force-push) |
| User | kswlt <3499874911@qq.com> |
