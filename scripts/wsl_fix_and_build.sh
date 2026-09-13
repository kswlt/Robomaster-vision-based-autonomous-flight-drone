#!/bin/bash
# Fix WSL environment: numpy<2 + build quadsim_cuda with --no-build-isolation
set -e

export http_proxy=http://172.22.0.1:7890
export https_proxy=http://172.22.0.1:7890
export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
VENV="$REPO/training/diffphys/venv"
UPSTREAM="$REPO/training/diffphys/upstream"

source "$VENV/bin/activate"

echo "=== Fix numpy version ==="
pip install "numpy<2" -q

echo "=== Verify torch ==="
python -c "import torch; print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())"

echo "=== Verify nvcc ==="
nvcc --version | tail -2

echo "=== Build quadsim_cuda extension (no build isolation) ==="
cd "$UPSTREAM/src"
pip install -e . --no-build-isolation 2>&1 | tail -20

echo "=== Verify quadsim_cuda ==="
cd "$UPSTREAM"
python -c "
import torch
import quadsim_cuda
print('quadsim_cuda functions:', [x for x in dir(quadsim_cuda) if not x.startswith('_')])
print('CUDA available:', torch.cuda.is_available())
print('ALL OK - DiffPhys environment ready')
"

echo "=== Setup complete ==="
