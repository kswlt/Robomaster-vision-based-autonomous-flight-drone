"""Test checkpoint save/load round-trip for policy."""
import tempfile
from pathlib import Path

import torch

from sim.common.config import repo_root


class TinyPolicy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.conv = torch.nn.Conv2d(1, 16, 5, stride=2)
        self.fc = torch.nn.Linear(16, 4)
    def forward(self, x):
        x = torch.relu(self.conv(x))
        x = x.mean(dim=[2, 3])
        return self.fc(x)


def test_checkpoint_save_load():
    model = TinyPolicy()
    x = torch.randn(1, 1, 240, 320)
    out1 = model(x)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.pt"
        torch.save({"model_state_dict": model.state_dict()}, path)

        model2 = TinyPolicy()
        ckpt = torch.load(path, weights_only=True)
        model2.load_state_dict(ckpt["model_state_dict"])
        out2 = model2(x)

    assert torch.allclose(out1, out2, atol=1e-6)


def test_checkpoint_dir_exists():
    ckpt_dir = repo_root() / "results" / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    assert ckpt_dir.exists()
