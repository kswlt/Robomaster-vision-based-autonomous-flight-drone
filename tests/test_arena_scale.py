"""Test arena scale calibration: unit = meters, 28x15m battlefield."""
import numpy as np
import trimesh

from sim.common.config import load_config, repo_root


def test_arena_config_unit():
    cfg = load_config("arena")
    assert cfg["arena"]["unit"] == "m"
    assert cfg["arena"]["arena_scale"] == 1.0
    assert cfg["arena"]["official_length_m"] == 28.0
    assert cfg["arena"]["official_width_m"] == 15.0


def test_stl_extents_match_official():
    """STL raw extents should be close to official + wall thickness."""
    mesh = trimesh.load(repo_root() / "assets/source/arena/rmuc_2026_arena.stl", force="mesh")
    extents = mesh.bounds[1] - mesh.bounds[0]
    # Official 28x15, STL includes walls (~1m extra)
    assert 27.0 < extents[0] < 31.0  # x
    assert 14.0 < extents[1] < 18.0  # y


def test_stray_artifact_clip():
    cfg = load_config("arena")
    assert cfg["arena"]["stray_artifact"]["present"] is True
    assert cfg["arena"]["stray_artifact"]["clip_z_max"] == 4.0
    # Verify artifact exists in STL
    mesh = trimesh.load(repo_root() / "assets/source/arena/rmuc_2026_arena.stl", force="mesh")
    high_verts = np.sum(mesh.vertices[:, 2] > 4.0)
    assert high_verts > 0, "Expected stray vertices above z=4"
