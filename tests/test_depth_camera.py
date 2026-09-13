"""Test DepthCamera: resolution, FOV, normalization, stats, synthetic depth."""
import numpy as np

from sim.common.config import load_config
from sim.isaac.depth_camera import DepthCamera


class FakeDrone:
    def __init__(self):
        self._pos = np.array([0.0, 0.0, 1.0])
    def get_position(self):
        return self._pos.copy()


def make_camera():
    cfg = load_config("depth_camera")
    return DepthCamera(cfg, FakeDrone())


def test_camera_resolution():
    cam = make_camera()
    assert cam.width == 320
    assert cam.height == 240
    assert cam.fov == 90.0


def test_synthetic_depth():
    cam = make_camera()
    depth = cam.get_depth()
    assert depth.shape == (240, 320)
    assert depth.dtype == np.float32


def test_inverse_depth_normalization():
    cam = make_camera()
    depth = np.array([[1.0, 2.0, 5.0]], dtype=np.float32)
    inv = cam.normalize(depth)
    assert abs(inv[0, 0] - 1.0) < 1e-6
    assert abs(inv[0, 1] - 0.5) < 1e-6


def test_depth_stats():
    cam = make_camera()
    depth = np.random.uniform(0.5, 10.0, (240, 320)).astype(np.float32)
    stats = cam.stats(depth)
    assert "min" in stats
    assert "max" in stats
    assert "valid_pixel_ratio" in stats
    assert "fps" in stats
    assert "timestamp" in stats
    assert stats["valid_pixel_ratio"] > 0.99
