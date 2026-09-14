#!/bin/bash
set -e

export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
VENV="$REPO/training/diffphys/venv"
UPSTREAM="$REPO/training/diffphys/upstream"
TARGET_ENV="$REPO/training/diffphys/target_env"
LOG_DIR="$REPO/results/diffphys_upstream"
mkdir -p "$LOG_DIR"

source "$VENV/bin/activate"

NUM_ITERS=${1:-10000}
echo "=== DiffPhys upstream training (1000-iter ckpt): $NUM_ITERS iters ==="

cd "$UPSTREAM"
PYTHONPATH="$UPSTREAM" python "$TARGET_ENV/main_upstream_ckpt.py" \
    --num_iters $NUM_ITERS \
    --batch_size 64 \
    --single \
    --speed_mtp 4 \
    --coef_d_acc 0.01 \
    --coef_d_jerk 0.001 \
    --ground_voxels \
    --random_rotation \
    --yaw_drift \
    --coef_collide 7.5 \
    --coef_obj_avoidance 3.0 \
    --cam_angle 20 \
    --fov_x_half_tan 0.82 \
    2>&1 | tail -5

echo "=== Checkpoints ==="
ls -la "$UPSTREAM/"checkpoint*.pth 2>/dev/null || echo "none"

echo "=== Verify checkpoint load ==="
python -c "
import torch, glob, sys
sys.path.insert(0, '$UPSTREAM')
from model import Model
ckpts = sorted(glob.glob('$UPSTREAM/checkpoint*.pth'))
if ckpts:
    f = ckpts[-1]
    print('Loading:', f)
    m = Model(10, 6)
    m.load_state_dict(torch.load(f, map_location='cpu'))
    m.eval()
    depth = torch.randn(2, 1, 12, 16)
    state = torch.randn(2, 10)
    hx = torch.zeros(2, 192)
    with torch.no_grad():
        act, _, hx2 = m(depth, state, hx)
    print('action shape:', act.shape, 'hidden shape:', hx2.shape)
    print('CHECKPOINT VERIFICATION PASSED')
else:
    print('No checkpoints found')
"
echo "=== DONE ==="
