"""Test action frame: body-frame acceleration + yaw rate, NOT PWM."""
import numpy as np

from sim.common.config import load_config
from sim.isaac.controller import ScriptedController
from sim.isaac.drone import Drone


def test_action_dim_and_scale():
    cfg = load_config("drone")
    assert cfg["drone"]["control"]["mode"] == "acceleration_yaw_rate"
    assert cfg["drone"]["control"]["action_dim"] == 4
    scale = cfg["drone"]["control"]["action_scale"]
    assert "ax" in scale and "ay" in scale and "az" in scale and "yaw_rate" in scale


def test_action_is_not_pwm():
    """Policy output must be high-level control, never 4 motor PWM values."""
    cfg = load_config("drone")
    action_names = list(cfg["drone"]["control"]["action_scale"].keys())
    assert "pwm" not in action_names
    assert "motor" not in action_names
    assert "ax" in action_names


def test_body_frame_rotation():
    """Controller output should rotate with drone yaw (body frame)."""
    ctrl = ScriptedController()
    goal = np.array([10.0, 0.0, 1.0])
    pos = np.array([0.0, 0.0, 1.0])
    vel = np.zeros(3)

    # Facing +x (yaw=0): acceleration should be mostly +x
    a1 = ctrl.compute_action(pos, vel, goal, drone_yaw=0.0)
    assert a1[0] > 0  # ax positive

    # Facing -x (yaw=pi): same world goal should give negative ax in body frame
    a2 = ctrl.compute_action(pos, vel, goal, drone_yaw=np.pi)
    assert a2[0] < 0  # ax negative (body forward is -x world)


def test_action_clipping():
    drone = Drone(load_config("drone"))
    # Extreme action should be clipped
    action = np.array([100.0, 100.0, 100.0, 100.0])
    drone.step(action)
    speed = np.linalg.norm(drone.get_velocity())
    assert speed <= drone.max_vel + 1e-6
