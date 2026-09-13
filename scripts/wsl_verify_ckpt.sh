#!/bin/bash
set -e

export PATH=/usr/local/cuda-11.8/bin:$PATH
REPO="/mnt/c/Users/Admin/Desktop/端到端强化学习无人机仿真"
source "$REPO/training/diffphys/venv/bin/activate"
cd "$REPO/training/diffphys/upstream"

python3 << 'PYEOF'
import torch, sys
sys.path.insert(0, ".")
from model import Model

ckpt = "checkpoint0003.pth"
print("Loading:", ckpt)
m = Model(10, 6)
state = torch.load(ckpt, map_location="cpu")
m.load_state_dict(state)
m.eval()
nparams = sum(p.numel() for p in m.parameters())
print("Model loaded, params:", nparams)

depth = torch.randn(4, 1, 12, 16)
state_vec = torch.randn(4, 10)
hx = torch.zeros(4, 192)
with torch.no_grad():
    act, _, hx2 = m(depth, state_vec, hx)
print("CPU forward: action", act.shape, "hidden", hx2.shape)
print("Action range: [%.3f, %.3f]" % (act.min().item(), act.max().item()))

m.cuda()
with torch.no_grad():
    act_g, _, hx_g2 = m(depth.cuda(), state_vec.cuda(), hx.cuda())
print("GPU forward: action", act_g.shape)
print("CHECKPOINT SAVE/LOAD VERIFICATION PASSED")
PYEOF
