#!/bin/bash
set -e

export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
VENV="$REPO/training/diffphys/venv"
LOG_DIR="$REPO/results/target_impact"
mkdir -p "$LOG_DIR" "$REPO/results/checkpoints"

source "$VENV/bin/activate"

NUM_ITERS=${1:-10000}
BATCH=${2:-64}

echo "=== Target-Impact Training: $NUM_ITERS iters, batch=$BATCH ==="
echo "Armor target: [3.08, 3.84, 1.5]"
echo "Curriculum: fixed target first 5000 iters, then randomization"

cd "$REPO/training/diffphys"

python target_env/train_target_impact.py \
    --num_iters $NUM_ITERS \
    --batch_size $BATCH \
    --lr 1e-3 \
    --timesteps 150 \
    --armor_x 3.08 \
    --armor_y 3.84 \
    --armor_z 1.5 \
    --hit_radius 0.3 \
    --min_impact_speed 2.0 \
    --max_impact_speed 10.0 \
    --coef_goal 2.0 \
    --coef_target_hit 10.0 \
    --coef_wrong_collision 5.0 \
    --coef_impact_vel 1.0 \
    --coef_impact_angle 2.0 \
    --coef_d_acc 0.01 \
    --coef_d_jerk 0.001 \
    --coef_v_pred 2.0 \
    --checkpoint_dir results/checkpoints \
    --save_interval 2000 \
    --log_interval 50 \
    2>&1 | tee "$LOG_DIR/train_${NUM_ITERS}iter.log"

echo "=== Training finished ==="
echo "=== Checkpoints ==="
ls -la "$REPO/results/checkpoints/"*.pth 2>/dev/null || echo "none"
echo "=== DONE ==="
