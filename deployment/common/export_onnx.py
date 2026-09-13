"""ONNX export for the trained DiffPhys policy.

PyTorch checkpoint -> ONNX (opset 17), fixed batch=1 for edge deployment.
Uses the real DiffPhys Model from upstream/model.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

# Add upstream to path for model import
REPO_ROOT = Path(__file__).resolve().parents[2]
UPSTREAM_DIR = REPO_ROOT / "training" / "diffphys" / "upstream"
sys.path.insert(0, str(UPSTREAM_DIR))

from model import Model  # noqa: E402


def export_onnx(checkpoint_path: str, output_path: str, opset: int = 18):
    """Export DiffPhys policy to ONNX with fixed input shapes."""
    print(f"[ONNX] Loading checkpoint: {checkpoint_path}")

    # Build model matching DiffPhys architecture: dim_obs=10, dim_action=6
    model = Model(dim_obs=10, dim_action=6)
    model.eval()

    # Load checkpoint
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
        model.load_state_dict(ckpt["model_state_dict"])
    elif isinstance(ckpt, dict) and "model" in ckpt:
        model.load_state_dict(ckpt["model"])
    else:
        model.load_state_dict(ckpt)
    print(f"[ONNX] Model loaded: {sum(p.numel() for p in model.parameters())} params")

    # Create ONNX-compatible wrapper (GRUCell is traceable)
    class PolicyONNX(torch.nn.Module):
        def __init__(self, base_model):
            super().__init__()
            self.base = base_model

        def forward(self, depth, state, hidden):
            # depth: (1, 1, 12, 16) - already maxpooled and normalized
            # state: (1, 10) - [local_v(3), target_v(3), gravity(3), margin(1)]
            # hidden: (1, 192) - GRU hidden state
            action, _, hidden_out = self.base(depth, state, hidden)
            # Return dummy values (not used in deployment)
            values = torch.zeros(action.shape[0], 1)
            return action, values, hidden_out

    onnx_model = PolicyONNX(model)
    onnx_model.eval()

    # Fixed inputs (batch=1) matching DiffPhys interface
    depth = torch.randn(1, 1, 12, 16)
    state = torch.randn(1, 10)
    hidden = torch.zeros(1, 192)

    # Verify forward pass
    with torch.no_grad():
        act, val, hid = onnx_model(depth, state, hidden)
    print(f"[ONNX] Forward pass OK: action={act.shape}, values={val}, hidden={hid.shape}")

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        onnx_model,
        (depth, state, hidden),
        str(out_path),
        opset_version=opset,
        input_names=["depth", "state", "gru_hidden"],
        output_names=["action", "values", "gru_hidden_out"],
        dynamic_axes=None,  # fixed batch for edge
    )
    print(f"[ONNX] Exported to {out_path}")

    # Validate
    try:
        import onnx
        onnx_model_loaded = onnx.load(str(out_path))
        onnx.checker.check_model(onnx_model_loaded)
        print("[ONNX] Model validation passed")

        # Print model info
        print(f"[ONNX] Inputs: {[i.name for i in onnx_model_loaded.graph.input]}")
        print(f"[ONNX] Outputs: {[o.name for o in onnx_model_loaded.graph.output]}")
    except ImportError:
        print("[ONNX] WARNING: onnx package not available, skipping validation")
    except Exception as e:
        print(f"[ONNX] Validation error: {e}")

    # ONNX Runtime inference test
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
        outputs = sess.run(None, {
            "depth": depth.numpy(),
            "state": state.numpy(),
            "gru_hidden": hidden.numpy(),
        })
        print(f"[ONNX Runtime] Inference OK: action shape={outputs[0].shape}")

        # Compare with PyTorch
        with torch.no_grad():
            pt_act, _, _ = onnx_model(depth, state, hidden)
        max_diff = np.max(np.abs(pt_act.numpy() - outputs[0]))
        print(f"[ONNX Runtime] Max diff vs PyTorch: {max_diff:.2e}")
    except ImportError:
        print("[ONNX Runtime] WARNING: onnxruntime not available, skipping inference test")
    except Exception as e:
        print(f"[ONNX Runtime] Inference test error: {e}")

    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default=str(REPO_ROOT / "training" / "diffphys" / "results" / "checkpoints" / "target_impact_0006k.pth"),
    )
    parser.add_argument("--output", default=str(REPO_ROOT / "deployment" / "onnx" / "policy.onnx"))
    parser.add_argument("--opset", type=int, default=18)
    args = parser.parse_args()
    export_onnx(args.checkpoint, args.output, args.opset)


if __name__ == "__main__":
    main()
