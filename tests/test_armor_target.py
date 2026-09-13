"""Test ArmorTarget: independent object, hit detection, center hit, angle."""
import numpy as np

from sim.common.config import load_config
from sim.isaac.armor_target import ArmorTarget


def make_armor():
    cfg = load_config("armor")
    return ArmorTarget(cfg)


def test_armor_position():
    armor = make_armor()
    pos = armor.get_position()
    assert pos.shape == (3,)
    assert np.allclose(pos, [3.08, 3.84, 1.5])


def test_armor_normal():
    armor = make_armor()
    normal = armor.get_normal()
    assert abs(np.linalg.norm(normal) - 1.0) < 1e-6


def test_hit_detection():
    armor = make_armor()
    assert armor.is_hit is False
    armor.mark_hit()
    assert armor.is_hit is True
    armor.reset()
    assert armor.is_hit is False


def test_center_hit():
    armor = make_armor()
    center = armor.get_position()
    assert armor.is_center_hit(center) is True
    far = center + np.array([1.0, 0, 0])
    assert armor.is_center_hit(far) is False


def test_impact_angle():
    armor = make_armor()
    # Velocity directly opposing normal = 0 degrees (head-on)
    vel = -armor.get_normal() * 5.0
    angle = armor.impact_angle_deg(vel)
    assert angle < 5.0
    # Velocity perpendicular to normal = 90 degrees
    perp = np.cross(armor.get_normal(), [0, 0, 1])
    if np.linalg.norm(perp) > 0:
        perp = perp / np.linalg.norm(perp) * 5.0
        angle = armor.impact_angle_deg(perp)
        assert 85.0 < angle < 95.0


def test_armor_independent_collider():
    cfg = load_config("armor")
    assert cfg["armor_target"]["collider"]["collision_group"] == "armor_target"
    assert cfg["armor_target"]["collider"]["report_contacts"] is True
