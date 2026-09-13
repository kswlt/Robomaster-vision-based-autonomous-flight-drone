#!/bin/bash
# Clone DiffPhysDrone upstream and set up WSL2 environment.
set -e

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
DIFFPHYS="$REPO/training/diffphys"
UPSTREAM="$DIFFPHYS/upstream"

cd "$DIFFPHYS"

# Remove placeholder .gitkeep so clone can proceed
rm -f "$UPSTREAM/.gitkeep"

# Clone if not already cloned
if [ ! -d "$UPSTREAM/.git" ]; then
    echo "=== Cloning DiffPhysDrone ==="
    git clone https://github.com/HenryHuYu/DiffPhysDrone upstream
fi

cd "$UPSTREAM"
SHA=$(git rev-parse HEAD)
echo "Pinned commit: $SHA"
echo "$SHA" > "$DIFFPHYS/upstream_commit.txt"

echo "=== Repo contents ==="
ls -la

echo "=== Key files ==="
for f in README.md main_cuda.py model.py env_cuda.py; do
    if [ -f "$f" ]; then
        echo "--- $f ($(wc -l < $f) lines) ---"
    else
        echo "--- $f NOT FOUND ---"
    fi
done

echo "=== CUDA extension files ==="
find . -name "*.cu" -o -name "*.cpp" -o -name "*.cuh" -o -name "setup.py" | head -20
