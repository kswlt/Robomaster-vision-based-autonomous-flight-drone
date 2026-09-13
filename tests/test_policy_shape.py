"""Test policy input/output shapes (CNN+GRU+MLP, RK3588-friendly)."""
import numpy as np
import torch

from sim.common.config import load_config


def test_policy_config_shapes():
    cfg = load_config("training")
    p = cfg["training"]["policy"]
    assert p["type"] == "cnn_gru_mlp"
    assert p["action_dim"] == 4  # ax, ay, az, yaw_rate
    assert p["gru"]["hidden_dim"] == 128
    assert p["cnn"]["input_channels"] == 1  # depth only


def test_observation_dim():
    cfg = load_config("training")
    obs = cfg["training"]["observation"]
    assert obs["depth"] is True
    assert obs["relative_goal"] is True
    assert obs["velocity"] is True
    assert obs["attitude_gravity"] is True
    # State vector: rel_goal(3) + velocity(3) + gravity(3) + angular_vel(3) = 12
    assert cfg["training"]["policy"]["mlp"]["state_input_dim"] == 12


def test_dummy_policy_forward():
    """Verify a small CNN+GRU+MLP produces correct output shapes."""
    class TinyPolicy(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = torch.nn.Conv2d(1, 16, 5, stride=2)
            self.gru = torch.nn.GRU(16, 128, batch_first=True)
            self.fc = torch.nn.Linear(128, 4)
        def forward(self, depth, hidden):
            x = torch.relu(self.conv(depth))
            x = x.mean(dim=[2, 3])
            x = x.unsqueeze(1)
            out, h = self.gru(x, hidden)
            return self.fc(out.squeeze(1)), h

    model = TinyPolicy()
    depth = torch.randn(1, 1, 240, 320)
    hidden = torch.zeros(1, 1, 128)
    action, h_out = model(depth, hidden)
    assert action.shape == (1, 4)
    assert h_out.shape == (1, 1, 128)
