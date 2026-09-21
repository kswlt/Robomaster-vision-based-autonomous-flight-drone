"""Level 0 numerical validation: PyTorch checkpoint vs deployed ONNX.

Loads upstream Model(dim_obs=10, dim_action=6) + checkpoint0004.pth, runs a
fixed set of deterministic inputs (single-frame and multi-frame GRU chains)
through both PyTorch and the deployed ONNX, and reports:
  max abs error, mean abs error, cosine similarity
for action and gru_hidden outputs.

Usage: python tools/validate_onnx_vs_torch.py [--ckpt ...] [--model ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training" / "diffphys" / "upstream"))

import torch  # noqa: E402
import onnxruntime as ort  # noqa: E402
from model import Model  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=str(
        ROOT / "training" / "diffphys" / "upstream" / "checkpoint0004.pth"))
    ap.add_argument("--model", default=str(
        ROOT / "deployment" / "onnx" / "upstream_avoidance.onnx"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    model = Model(dim_obs=10, dim_action=6)
    model.eval()
    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
        model.load_state_dict(ckpt["model_state_dict"])
    elif isinstance(ckpt, dict) and "model" in ckpt:
        model.load_state_dict(ckpt["model"])
    else:
        model.load_state_dict(ckpt)

    sess = ort.InferenceSession(args.model, providers=["CPUExecutionProvider"])

    # --- fixed test inputs (deterministic, seed saved) ---
    cases = []
    # all-far (empty), all-near, random gaussian, benchmark-like frontal wall
    far = np.full((1, 1, 12, 16), 3.0 / 24.0 - 0.6, np.float32)
    near = np.full((1, 1, 12, 16), 3.0 / 0.35 - 0.6, np.float32)
    cases += [("far", far), ("near", near)]
    for k in range(6):
        cases.append((f"rand{k}", rng.standard_normal((1, 1, 12, 16)).astype(np.float32)))
    wall = np.full((1, 1, 12, 16), 3.0 / 24.0 - 0.6, np.float32)
    wall[:, :, 6:10, :] = 3.0 / 1.0 - 0.6
    cases.append(("frontal_1m", wall))

    states = [
        np.zeros((1, 10), np.float32),
        np.array([[0, 0, 0, 1.5, 0, 0, 0, 0, 1, 0.2]], np.float32),
        np.array([[0.3, -0.1, 0, 1.5, 0, 0, 0.1, -0.2, 0.97, 0.1]], np.float32),
    ]

    def torch_run(depth, state, hidden):
        with torch.no_grad():
            a, _, h = model(torch.from_numpy(depth), torch.from_numpy(state),
                            None if hidden is None else torch.from_numpy(hidden))
        return a.numpy(), h.numpy()

    def onnx_run(depth, state, hidden):
        if hidden is None:
            hidden = np.zeros((1, 192), np.float32)
        out = sess.run(None, {"depth": depth, "state": state, "gru_hidden": hidden})
        return out[0], out[2]

    results = []
    for name, depth in cases:
        for si, state in enumerate(states):
            h0 = None
            a_t, h_t = torch_run(depth, state, h0)
            a_o, h_o = onnx_run(depth, state, h0)
            results.append(_compare(f"{name}/s{si}/1step", a_t, h_t, a_o, h_o))

    # multi-step chain (5 frames) with hidden-state feedback
    a_t_chain, a_o_chain = [], []
    h_t, h_o = None, np.zeros((1, 192), np.float32)
    for i in range(5):
        depth = cases[i % len(cases)][1]
        a_t, h_t = torch_run(depth, states[i % 3], h_t)
        a_o, h_o = onnx_run(depth, states[i % 3], h_o)
        a_t_chain.append(a_t)
        a_o_chain.append(a_o)
    results.append(_compare("chain/5steps", np.stack(a_t_chain), h_t,
                            np.stack(a_o_chain), h_o))

    worst = max(results, key=lambda r: r["max_abs_action"])
    print(f"cases: {len(results)}   worst max_abs_action: {worst['max_abs_action']:.3e}")
    for r in results:
        if r["max_abs_action"] > 1e-5 or r["max_abs_hidden"] > 1e-5:
            print(f"  {r['name']:22s} act_max={r['max_abs_action']:.2e} "
                  f"act_mean={r['mean_abs_action']:.2e} cos={r['cos_action']:.6f} "
                  f"hid_max={r['max_abs_hidden']:.2e}")
    print(f"  {'(all others within 1e-5)' if all(r['max_abs_action'] <= 1e-5 and r['max_abs_hidden'] <= 1e-5 for r in results) else ''}")
    return results


def _compare(name, a_t, h_t, a_o, h_o):
    a_t = np.asarray(a_t, np.float32).reshape(-1)
    a_o = np.asarray(a_o, np.float32).reshape(-1)
    h_t = np.asarray(h_t, np.float32).reshape(-1)
    h_o = np.asarray(h_o, np.float32).reshape(-1)
    cos = float(np.dot(a_t, a_o) / (np.linalg.norm(a_t) * np.linalg.norm(a_o) + 1e-12))
    return {
        "name": name,
        "max_abs_action": float(np.max(np.abs(a_t - a_o))),
        "mean_abs_action": float(np.mean(np.abs(a_t - a_o))),
        "cos_action": cos,
        "max_abs_hidden": float(np.max(np.abs(h_t - h_o))),
    }


if __name__ == "__main__":
    main()
