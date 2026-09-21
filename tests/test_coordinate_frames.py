"""Coordinate-frame unit tests for the deployment policy.

Validates that the deployment's observation/action math is identical to the
upstream DiffPhys training semantics and that all sign conventions follow from
the PX4/MAVLink attitude definitions — no empirical sign flips.

Conventions under test (all defined in deployment/common/upstream_obs.py):
  - world = NEU (x=north, y=east, z=up), converted from PX4 LOCAL_NED by z flip
  - PX4/MAVLink attitude: roll + = right roll, pitch + = nose up, yaw + = right
  - training frame R = [fwd, left=cross(up,fwd), up], yaw-only
  - state[6:9] = TRUE body-up in world (from full attitude), NOT constant
"""
import numpy as np
import pytest

from deployment.common import upstream_obs as uo

DEG = np.pi / 180.0
ALLCLOSE = dict(rtol=1e-6, atol=1e-6)


def norm(v):
    return np.asarray(v, dtype=np.float64) / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# yaw-only frame
# ---------------------------------------------------------------------------
def test_yaw_frame_orthonormal():
    for yaw in np.linspace(-np.pi, np.pi, 9):
        R = uo.yaw_only_frame(float(yaw))
        assert np.allclose(R.T @ R, np.eye(3), **ALLCLOSE)
        assert np.allclose(np.linalg.det(R), 1.0, **ALLCLOSE)


def test_yaw_frame_nose_north():
    R = uo.yaw_only_frame(0.0)
    assert np.allclose(R[:, 0], [1, 0, 0], **ALLCLOSE)   # fwd = north
    assert np.allclose(R[:, 1], [0, 1, 0], **ALLCLOSE)   # second axis = east
    assert np.allclose(R[:, 2], [0, 0, 1], **ALLCLOSE)   # up


def test_yaw_frame_nose_east():
    R = uo.yaw_only_frame(90 * DEG)
    assert np.allclose(R[:, 0], [0, 1, 0], **ALLCLOSE)   # fwd = east
    assert np.allclose(R[:, 1], [-1, 0, 0], **ALLCLOSE)  # second axis = west
    assert np.allclose(R[:, 2], [0, 0, 1], **ALLCLOSE)


def test_yaw_frame_matches_training_construction():
    """Training: fwd = horizontal projection of body forward, normalized;
    left = cross(up, fwd).  For the textbook Euler DCM the projection equals
    [cos(yaw), sin(yaw), 0], which is what yaw_only_frame builds."""
    for roll, pitch, yaw in [(0.0, 0.0, 0.5), (0.3, -0.2, 1.1), (-0.5, 0.4, -2.0)]:
        R_nb = uo.ned_to_body_dcm(roll, pitch, yaw)
        fwd_ned = R_nb[0]                      # body forward in NED
        fwd_neu = np.array([fwd_ned[0], fwd_ned[1], -fwd_ned[2]])
        proj = norm(np.array([fwd_neu[0], fwd_neu[1], 0.0]))
        assert np.allclose(proj, uo.yaw_only_frame(yaw)[:, 0], **ALLCLOSE)


# ---------------------------------------------------------------------------
# NED->body DCM vs quaternion
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("roll,pitch,yaw", [
    (0.0, 0.0, 0.0), (30 * DEG, 0.0, 0.0), (-30 * DEG, 0.0, 0.0),
    (0.0, 30 * DEG, 0.0), (0.0, -30 * DEG, 0.0), (0.0, 0.0, 90 * DEG),
    (10 * DEG, -20 * DEG, 45 * DEG), (-15 * DEG, 25 * DEG, -60 * DEG),
    (40 * DEG, 30 * DEG, 120 * DEG), (170 * DEG, 5 * DEG, 10 * DEG),
])
def test_dcm_matches_quaternion(roll, pitch, yaw):
    R_e = uo.ned_to_body_dcm(roll, pitch, yaw)
    q = uo.euler_to_quaternion(roll, pitch, yaw)
    R_q = uo.dcm_from_quaternion(*q)
    assert np.allclose(R_e, R_q, atol=1e-9)


def test_body_axes_level():
    R = uo.ned_to_body_dcm(0, 0, 0)
    assert np.allclose(R, np.eye(3), **ALLCLOSE)
    assert np.allclose(uo.body_up_world_neu(0, 0, 0), [0, 0, 1], **ALLCLOSE)


# ---------------------------------------------------------------------------
# body-up sign conventions (user-required cases: 机头朝北/朝东, roll/pitch/yaw +-)
# ---------------------------------------------------------------------------
def test_body_up_pitch_positive_nose_up():
    # nose up 30 deg, nose north: top tilts BACKWARD (south = -x)
    up = uo.body_up_world_neu(0.0, 30 * DEG, 0.0)
    assert np.allclose(up, [-np.sin(30 * DEG), 0.0, np.cos(30 * DEG)], **ALLCLOSE)


def test_body_up_pitch_negative_nose_down():
    # nose down 30 deg, nose north: top tilts FORWARD (north = +x)
    up = uo.body_up_world_neu(0.0, -30 * DEG, 0.0)
    assert np.allclose(up, [np.sin(30 * DEG), 0.0, np.cos(30 * DEG)], **ALLCLOSE)


def test_body_up_roll_positive_right():
    # roll right 30 deg: right side down, rotor-plane top normal tilts toward
    # the downhill side = EAST (+y).  (Same rule as the nose-up case: the
    # surface normal tilts toward the LOW side.)
    up = uo.body_up_world_neu(30 * DEG, 0.0, 0.0)
    assert np.allclose(up, [0.0, np.sin(30 * DEG), np.cos(30 * DEG)], **ALLCLOSE)


def test_body_up_roll_negative_left():
    # roll left 30 deg: top normal tilts WEST (-y)
    up = uo.body_up_world_neu(-30 * DEG, 0.0, 0.0)
    assert np.allclose(up, [0.0, -np.sin(30 * DEG), np.cos(30 * DEG)], **ALLCLOSE)


def test_body_up_yaw_rotation_preserves_tilt_azimuth():
    # nose east + pitch up: top tilts toward body-back = west? (fwd=east, so
    # top tilts to -fwd = west)  -- cross-check azimuth via DCM rows
    up = uo.body_up_world_neu(0.0, 30 * DEG, 90 * DEG)
    # body-down in NED third row = (0, sin30, cos30) -> up_world = (0,-sin30,cos30)
    assert np.allclose(up, [0.0, -np.sin(30 * DEG), np.cos(30 * DEG)], **ALLCLOSE)


def test_body_up_from_quaternion_matches_euler():
    for roll, pitch, yaw in [(0.1, -0.3, 0.7), (-0.4, 0.2, 2.0), (0.5, 0.5, -1.0)]:
        q = uo.euler_to_quaternion(roll, pitch, yaw)
        assert np.allclose(uo.body_up_world_from_quaternion(*q),
                           uo.body_up_world_neu(roll, pitch, yaw), **ALLCLOSE)


# ---------------------------------------------------------------------------
# velocity / target / acceleration projections
# ---------------------------------------------------------------------------
def test_local_v_projection_recovers_body_components():
    yaw = 37 * DEG
    R = uo.yaw_only_frame(yaw)
    for v_world, expect in [
        (R[:, 0], [1, 0, 0]),   # velocity along fwd -> [fwd,0,0]
        (R[:, 1], [0, 1, 0]),   # velocity along second axis
        (R[:, 2], [0, 0, 1]),   # velocity along up
    ]:
        local = R.T @ np.asarray(v_world, dtype=np.float64)
        assert np.allclose(local, expect, **ALLCLOSE)


def test_target_velocity_clamp():
    t = np.array([3.0, 4.0, 0.0])  # norm 5
    out = uo.clamp_target_velocity(t, 1.5)
    assert np.isclose(np.linalg.norm(out), 1.5)
    assert np.allclose(out, t / 5.0 * 1.5, **ALLCLOSE)
    # no clamp when below max
    assert np.allclose(uo.clamp_target_velocity(t, 10.0), t, **ALLCLOSE)


def test_decode_action_world_mapping():
    """Raw 6-dim layout is INTERLEAVED [a_x, v_x, a_y, v_y, a_z, v_z]
    (upstream: act.reshape(B,3,-1), col0 = (e0,e2,e4) = a_pred)."""
    yaw = 0.0
    R = uo.yaw_only_frame(yaw)
    raw = np.array([1.0, 0.5, 0.0, 0.0, 0.0, 0.0])  # a=[1,0,0], v=[0.5,0,0]
    out = uo.decode_action(raw, R)
    assert np.allclose(out['accel_body'], [1, 0, 0], **ALLCLOSE)
    assert np.allclose(out['accel_world'], [1, 0, 0], **ALLCLOSE)
    assert np.allclose(out['vpred_world'], [0.5, 0, 0], **ALLCLOSE)
    # training decode: net = R@(a_pred - v_pred)   (== (a-v-g)+g for thr=1)
    assert np.allclose(out['net_accel_world'], [0.5, 0, 0], **ALLCLOSE)


def test_decode_action_nose_east():
    R = uo.yaw_only_frame(90 * DEG)
    raw = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])  # a=[0,1,0] (2nd axis)
    out = uo.decode_action(raw, R)
    # 2nd frame axis = west for nose-east -> world accel must be west
    assert np.allclose(out['accel_world'], [-1, 0, 0], **ALLCLOSE)


def test_state_shape_and_slots():
    R = uo.yaw_only_frame(0.3)
    state = uo.build_state([0.1, 0.2, 0.3], [1.0, 0.0, 0.5],
                           uo.body_up_world_neu(0.1, -0.2, 0.3), 0.2, R=R)
    assert state.shape == (10,)
    assert np.isclose(state[9], 0.2)
    assert np.allclose(state[6:9], uo.body_up_world_neu(0.1, -0.2, 0.3), **ALLCLOSE)


# ---------------------------------------------------------------------------
# NED <-> NEU conversions (as used in web_vis.py)
# ---------------------------------------------------------------------------
def test_ned_to_neu_conversion():
    ned_pos = np.array([1.0, 2.0, 3.0])   # z down
    neu_pos = np.array([ned_pos[0], ned_pos[1], -ned_pos[2]])
    assert np.allclose(neu_pos, [1, 2, -3])
    # acceleration command NED -> NEU
    ned_acc = np.array([0.5, -0.5, -9.8])
    neu_acc = np.array([ned_acc[0], ned_acc[1], -ned_acc[2]])
    assert np.allclose(neu_acc, [0.5, -0.5, 9.8])
