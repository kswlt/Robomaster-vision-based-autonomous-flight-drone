#!/bin/bash
# Set up WSL2 environment for DiffPhysDrone training.
# Python 3.10, PyTorch CUDA, build quadsim_cuda extension.
set -e

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
DIFFPHYS="$REPO/training/diffphys"
UPSTREAM="$DIFFPHYS/upstream"
VENV="$DIFFPHYS/venv"

cd "$DIFFPHYS"

echo "=== WSL system info ==="
python3 --version
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "nvidia-smi not available"
which nvcc 2>/dev/null && nvcc --version | tail -2 || echo "nvcc not found in PATH"

echo "=== Creating venv ==="
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install --upgrade pip

echo "=== Installing PyTorch (CUDA 11.8, matching upstream) ==="
pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu118

echo "=== Installing dependencies ==="
pip install matplotlib tqdm tensorboard pyyaml numpy scipy

echo "=== Verifying torch CUDA ==="
python -c "import torch; print('torch', torch.__version__, 'cuda_available:', torch.cuda.is_available(), 'device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"

echo "=== Building CUDA extension (quadsim_cuda) ==="
cd "$UPSTREAM/src"
pip install -e . 2>&1 | tail -20

echo "=== Verifying quadsim_cuda import ==="
cd "$UPSTREAM"
python -c "import quadsim_cuda; print('quadsim_cuda OK:', dir(quadsim_cuda))"

echo "=== Setup complete ==="
