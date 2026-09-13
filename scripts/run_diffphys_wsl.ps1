# run_diffphys_wsl.ps1 - Clone and run DiffPhysDrone training in WSL2
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run_diffphys_wsl.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$WslRepo = "/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
$DiffPhysDir = "$WslRepo/training/diffphys"

Write-Output "=== DiffPhysDrone training in WSL2 ==="

# Check WSL GPU
wsl -e bash -lc "nvidia-smi --query-gpu=name --format=csv,noheader || echo 'GPU not accessible in WSL'"

# Clone upstream if not present
wsl -e bash -lc @"
set -e
cd '$DiffPhysDir'
if [ ! -d 'upstream/.git' ]; then
    echo 'Cloning DiffPhysDrone...'
    git clone https://github.com/HenryHuYu/DiffPhysDrone upstream
    cd upstream
    git rev-parse HEAD > ../upstream_commit.txt
    echo \"Pinned commit: \$(cat ../upstream_commit.txt)\"
else
    echo 'Upstream already cloned.'
    cd upstream
    git rev-parse HEAD > ../upstream_commit.txt
fi
"@

# Set up Python venv and dependencies
wsl -e bash -lc @"
set -e
cd '$DiffPhysDir'
if [ ! -d 'venv' ]; then
    echo 'Creating Python 3.10 venv...'
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
echo 'Installing PyTorch (CUDA)...'
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install numpy scipy matplotlib pyyaml
echo 'Building CUDA extension...'
cd upstream
if [ -f 'setup.py' ]; then
    python setup.py build_ext --inplace || echo 'CUDA extension build may need manual fix'
fi
echo 'Environment ready.'
python -c 'import torch; print(\"torch\", torch.__version__, \"cuda:\", torch.cuda.is_available())'
"@

Write-Output "=== DiffPhys setup complete ==="
Write-Output "To run training: wsl -e bash -lc 'cd $DiffPhysDir && source venv/bin/activate && cd upstream && python main_cuda.py'"
