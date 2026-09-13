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

echo "=== Install build deps (wheel, ninja) ==="
pip install wheel ninja -q

echo "=== numpy ==="
python -c "import numpy; print('numpy', numpy.__version__)"

echo "=== torch ==="
python -c "import torch; print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())"

echo "=== nvcc ==="
nvcc --version | grep release

echo "=== Build quadsim_cuda via setup.py build_ext --inplace ==="
cd "$UPSTREAM/src"
python setup.py build_ext --inplace 2>&1 | tee /tmp/build_log.txt
BUILD_EXIT=${PIPESTATUS[0]}

echo "=== Build exit code: $BUILD_EXIT ==="

if [ $BUILD_EXIT -ne 0 ]; then
    echo "BUILD FAILED - last 50 lines:"
    tail -50 /tmp/build_log.txt
    exit 1
fi

echo "=== Built files ==="
ls -la "$UPSTREAM/src/"*.so 2>/dev/null || echo "No .so found in src"
find "$UPSTREAM/src" -name "*.so" -type f

echo "=== Copy .so to site-packages ==="
SO_FILE=$(find "$UPSTREAM/src" -name "quadsim_cuda*.so" -type f | head -1)
if [ -n "$SO_FILE" ]; then
    SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
    cp "$SO_FILE" "$SITE_PACKAGES/"
    echo "Copied to $SITE_PACKAGES/"
else
    echo "ERROR: No .so file found!"
    exit 1
fi

echo "=== Verify quadsim_cuda import ==="
cd "$UPSTREAM"
python -c "
import torch
import quadsim_cuda
print('quadsim_cuda imported successfully')
print('functions:', [x for x in dir(quadsim_cuda) if not x.startswith('_')])
print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())
print('ALL CHECKS PASSED - DiffPhys environment ready')
"

echo "=== DONE ==="
