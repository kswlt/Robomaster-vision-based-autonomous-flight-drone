"""ONNX export for the trained policy.

PyTorch checkpoint -> ONNX (opset 17), fixed batch=1 for edge deployment.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch

from sim.common.config import repo_root


def export_onnx(checkpoint_path: str, output_path: str, opset: int = 17):
    """Export policy to ONNX with fixed input shapes."""
    # Load checkpoint and rebuild model (placeholder — actual model class in training/policy/)
    # This is a skeleton; fill in when policy class is finalized.
    print(f"[ONNX] Loading checkpoint: {checkpoint_path}")

    # Dummy model for export validation (replace with real policy)
    class DummyPolicy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = torch.nn.Conv2d(1, 16, 5, stride=2)
            self.gru = torch.nn.GRU(128, 128, batch_first=True)
            self.fc = torch.nn.Linear(128, 4)

        def forward(self, depth, state, hidden):
            x = torch.relu(self.conv(depth))
            x = x.mean(dim=[2, 3])  # global pool -> 16
            x = torch.nn.functional.pad(x, (0, 112))  # pad to 128
            x = x.unsqueeze(1)  # seq len 1
            out, hidden = self.gru(x, hidden)
            action = self.fc(out.squeeze(1))
            return action, hidden

    model = DummyPolicy()
    model.eval()

    # Fixed inputs (batch=1)
    depth = torch.randn(1, 1, 240, 320)
    state = torch.randn(1, 12)
    hidden = torch.zeros(1, 1, 128)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        (depth, state, hidden),
        str(out_path),
        opset_version=opset,
        input_names=["depth", "state", "gru_hidden"],
        output_names=["action", "gru_hidden_out"],
        dynamic_axes=None,  # fixed batch for edge
    )
    print(f"[ONNX] Exported to {out_path}")

    # Validate
    import onnx
    onnx_model = onnx.load(str(out_path))
    onnx.checker.check_model(onnx_model)
    print("[ONNX] Model validation passed")
    return out_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="results/checkpoints/best.pt")
    parser.add_argument("--output", default="deployment/onnx/policy.onnx")
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()
    export_onnx(args.checkpoint, args.output, args.opset)


if __name__ == "__main__":
    main()
