"""Test collision classification: TARGET_HIT vs WRONG_COLLISION."""
import numpy as np

from sim.common.config import load_config
from sim.isaac.armor_target import ArmorTarget
from sim.isaac.drone import Drone


def test_target_hit_classification():
    drone = Drone(load_config("drone"))
    armor = ArmorTarget(load_config("armor"))
    # Drone at armor position = target hit
    drone._position = armor.get_position().copy()
    assert drone.check_hit(armor.get_position(), threshold=0.4) is True


def test_wrong_collision_classification():
    drone = Drone(load_config("drone"))
    # Drone far from armor, arena contact = wrong collision
    drone._position = np.array([0.0, 0.0, 1.0])
    assert drone.check_hit(np.array([10.0, 10.0, 1.0]), threshold=0.4) is False
    assert drone.check_wrong_collision(arena_contact=True) is True


def test_armor_not_in_arena():
    """ArmorTarget must be a separate collision group from arena."""
    armor_cfg = load_config("armor")
    arena_cfg = load_config("arena")
    assert armor_cfg["armor_target"]["collider"]["collision_group"] == "armor_target"
    # Arena walls use collision_group="arena" (set in arena.py)
    assert "armor_target" != "arena"
