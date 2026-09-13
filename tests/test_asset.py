"""Test asset integrity: files exist, SHA256 matches, STL loads."""
import hashlib
from pathlib import Path

import trimesh

from sim.common.config import repo_root

ASSETS = {
    "assets/source/arena/rmuc_2026_arena.stl": "D7DBB7DD0862D81BE6FF2DFA004A20ED8839E39636E475E97EB06EF61E25CEF6",
    "assets/source/armor/armor_bracket_spec_1.png": "905323B0A7127B2107C85E7D0BFA486709E4F17A6CAB255478535C810A4CDE31",
    "assets/source/armor/armor_rigid_mount_spec_2.png": "2E0100F781AD01C4DE38AFF439004AB7BE59288618B4ADDD9B1279779EA56819",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def test_assets_exist():
    for rel in ASSETS:
        assert (repo_root() / rel).exists(), f"Missing asset: {rel}"


def test_asset_sha256():
    for rel, expected in ASSETS.items():
        actual = sha256(repo_root() / rel)
        assert actual == expected, f"SHA256 mismatch for {rel}: {actual} != {expected}"


def test_stl_loads():
    mesh = trimesh.load(repo_root() / "assets/source/arena/rmuc_2026_arena.stl", force="mesh")
    assert len(mesh.faces) == 124995
    assert len(mesh.vertices) == 116893


def test_stl_extents():
    mesh = trimesh.load(repo_root() / "assets/source/arena/rmuc_2026_arena.stl", force="mesh")
    extents = mesh.bounds[1] - mesh.bounds[0]
    assert abs(extents[0] - 29.15) < 0.1  # x ~ 29.15m
    assert abs(extents[1] - 16.05) < 0.1  # y ~ 16.05m
