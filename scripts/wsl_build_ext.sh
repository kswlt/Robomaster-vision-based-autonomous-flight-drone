#!/bin/bash
set -e

export http_proxy=http://172.22.0.1:7890
export https_proxy=http://172.22.0.1:7890
export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
VENV="$REPO/training/diffphys/venv"
UPSTREAM="$REPO/training/diffphys/upstream"

source "$VENV/bin/activate"

echo "=== numpy version ==="
python -c "import numpy; print('numpy', numpy.__version__)"

echo "=== torch ==="
python -c "import torch; print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())"

echo "=== nvcc ==="
nvcc --version | grep release

echo "=== Build quadsim_cuda (non-editable, no build isolation) ==="
cd "$UPSTREAM/src"
pip install . --no-build-isolation 2>&1 | tee /tmp/build_log.txt
BUILD_EXIT=$?

echo "=== Build exit code: $BUILD_EXIT ==="
echo "=== Last 30 lines of build log ==="
cat /tmp/build_log.txt | tail -30

if [ $BUILD_EXIT -ne 0 ]; then
    echo "BUILD FAILED"
    exit 1
fi

echo "=== Verify quadsim_cuda ==="
cd "$UPSTREAM"
python -c "
import torch
import quadsim_cuda
print('quadsim_cuda imported successfully')
print('functions:', [x for x in dir(quadsim_cuda) if not x.startswith('_')])
print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())
print('ALL CHECKS PASSED')
"

echo "=== DONE ==="
