#!/bin/bash
set -e

export http_proxy=http://172.22.0.1:7890
export https_proxy=http://172.22.0.1:7890
export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH
export MAX_JOBS=4

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
VENV="$REPO/training/diffphys/venv"
UPSTREAM="$REPO/training/diffphys/upstream"
NATIVE_BUILD="$HOME/diffphys_build"

source "$VENV/bin/activate"

echo "=== Copy source to WSL native filesystem ==="
rm -rf "$NATIVE_BUILD"
mkdir -p "$NATIVE_BUILD"
cp "$UPSTREAM/src/quadsim.cpp" "$NATIVE_BUILD/"
cp "$UPSTREAM/src/quadsim_kernel.cu" "$NATIVE_BUILD/"
cp "$UPSTREAM/src/dynamics_kernel.cu" "$NATIVE_BUILD/"
cp "$UPSTREAM/src/setup.py" "$NATIVE_BUILD/"
ls -la "$NATIVE_BUILD/"

echo "=== numpy ==="
python -c "import numpy; print('numpy', numpy.__version__)"

echo "=== torch ==="
python -c "import torch; print('torch', torch.__version__, 'cuda:', torch.cuda.is_available())"

echo "=== nvcc ==="
nvcc --version | grep release

echo "=== Build quadsim_cuda on native filesystem ==="
cd "$NATIVE_BUILD"
python setup.py build_ext --inplace 2>&1 | tee /tmp/build_log.txt
BUILD_EXIT=${PIPESTATUS[0]}

echo "=== Build exit code: $BUILD_EXIT ==="

if [ $BUILD_EXIT -ne 0 ]; then
    echo "BUILD FAILED - last 50 lines:"
    tail -50 /tmp/build_log.txt
    exit 1
fi

echo "=== Built files ==="
ls -la "$NATIVE_BUILD/"*.so

echo "=== Copy .so to site-packages ==="
SO_FILE=$(find "$NATIVE_BUILD" -name "quadsim_cuda*.so" -type f | head -1)
SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
cp "$SO_FILE" "$SITE_PACKAGES/"
echo "Copied to $SITE_PACKAGES/"

echo "=== Also copy to upstream/src for reference ==="
cp "$SO_FILE" "$UPSTREAM/src/"

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
