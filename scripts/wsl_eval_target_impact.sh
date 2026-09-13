#!/bin/bash
set -e

export PATH=/usr/local/cuda-11.8/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH

REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
VENV="$REPO/training/diffphys/venv"
CKPT="$REPO/training/diffphys/results/checkpoints/target_impact_0006k.pth"
OUTPUT="$REPO/results/target_impact_eval_1000ep.json"

source "$VENV/bin/activate"
cd "$REPO/training/diffphys"

echo "=== Target-Impact Evaluation: 1000 episodes ==="
echo "Checkpoint: $CKPT"
echo "Output: $OUTPUT"

python target_env/eval_target_impact.py \
    --checkpoint "$CKPT" \
    --episodes 1000 \
    --batch_size 128 \
    --timesteps 200 \
    --armor_x 3.08 \
    --armor_y 3.84 \
    --armor_z 1.5 \
    --hit_radius 0.3 \
    --center_radius 0.1 \
    --output "$OUTPUT"

echo "=== Evaluation complete ==="
cat "$OUTPUT"
