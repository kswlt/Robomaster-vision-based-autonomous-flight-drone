"""Test episode reset: drone returns to initial state, armor unhit."""
import numpy as np

from sim.common.config import load_config
from sim.isaac.armor_target import ArmorTarget
from sim.isaac.drone import Drone
from sim.isaac.episode import EpisodeRunner


def test_episode_reset():
    drone = Drone(load_config("drone"))
    armor = ArmorTarget(load_config("armor"))
    eval_cfg = load_config("evaluation")
    runner = EpisodeRunner(drone, armor, None, None, eval_cfg)

    # Modify state
    drone._position = np.array([5.0, 5.0, 3.0])
    drone._velocity = np.array([2.0, 0, 0])
    armor.mark_hit()

    # Reset
    runner.reset(episode_id=0)

    # Verify
    assert np.allclose(drone.get_position(), drone.init_pos)
    assert np.allclose(drone.get_velocity(), np.zeros(3))
    assert armor.is_hit is False
    assert runner.state == "TAKEOFF"
    assert runner.result.episode_id == 0


def test_episode_state_machine():
    drone = Drone(load_config("drone"))
    armor = ArmorTarget(load_config("armor"))
    eval_cfg = load_config("evaluation")
    runner = EpisodeRunner(drone, armor, None, None, eval_cfg)
    runner.reset(0)
    assert runner.state == "TAKEOFF"
    # States list is correct
    assert runner.STATES == ["TAKEOFF", "ATTACK", "HIT", "RECOVER", "RETURN", "HOME"]
