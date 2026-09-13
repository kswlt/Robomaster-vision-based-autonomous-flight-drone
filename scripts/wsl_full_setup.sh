#!/bin/bash
# Full WSL2 setup: proxy + CUDA 11.8 + PyTorch + quadsim_cuda extension
set -e

# Proxy config
export http_proxy=http://172.22.0.1:7890
export https_proxy=http://172.22.0.1:7890
export HTTP_PROXY=http://172.22.0.1:7890
export HTTPS_PROXY=http://172.22.0.1:7890
export no_proxy=localhost,127.0.0.1

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
DIFFPHYS="$REPO/training/diffphys"
UPSTREAM="$DIFFPHYS/upstream"
VENV="$DIFFPHYS/venv"

echo "=== Step 1: Install CUDA Toolkit 11.8 ==="
if [ ! -f /usr/local/cuda-11.8/bin/nvcc ]; then
    echo "Downloading CUDA 11.8 WSL repo..."
    wget -q https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin -O /tmp/cuda-wsl-ubuntu.pin
    sudo mv /tmp/cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
    wget -q https://developer.download.nvidia.com/compute/cuda/11.8.0/local_installers/cuda-repo-wsl-ubuntu-11-8-local_11.8.0-1_amd64.deb -O /tmp/cuda-repo.deb
    sudo dpkg -i /tmp/cuda-repo.deb
    sudo cp /var/cuda-repo-wsl-ubuntu-11-8-local/cuda-*-keyring.gpg /usr/share/keyrings/ 2>/dev/null || true
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cuda-toolkit-11-8
    echo "CUDA 11.8 installed"
else
    echo "CUDA 11.8 already installed"
fi
export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH
nvcc --version | tail -2

echo "=== Step 2: Create venv and install PyTorch ==="
cd "$DIFFPHYS"
if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
pip install --upgrade pip -q

echo "Installing PyTorch 2.2.2+cu118..."
pip install torch==2.2.2 torchvision==0.17.2 --index-url https://download.pytorch.org/whl/cu118 -q

echo "Installing dependencies..."
pip install matplotlib tqdm tensorboard pyyaml numpy scipy -q

python -c "import torch; print('torch', torch.__version__, 'cuda:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

echo "=== Step 3: Build quadsim_cuda extension ==="
cd "$UPSTREAM/src"
pip install -e . 2>&1 | tail -15

echo "=== Step 4: Verify ==="
cd "$UPSTREAM"
python -c "
import torch
import quadsim_cuda
print('quadsim_cuda functions:', [x for x in dir(quadsim_cuda) if not x.startswith('_')])
print('CUDA available:', torch.cuda.is_available())
print('ALL OK')
"

echo "=== Setup complete ==="
