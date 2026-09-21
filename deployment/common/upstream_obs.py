"""Upstream DiffPhys avoidance policy — training-exact observation/action module.

Single source of truth for mapping between the upstream DiffPhysDrone training
semantics (commit 2719361) and the real-drone deployment on Orange Pi 5.

All quantities here are derived from upstream source, NOT from variable names:

Training (main_cuda.py / main_upstream_ckpt.py + env_cuda.py):
  - Frame R used to express local_v / target_v / action: yaw-only frame
      fwd  = normalize(body_forward projected to horizontal plane)
      left = cross(up, fwd)          (up = [0,0,1], world z-up)
      up   = [0,0,1]
      R    = stack([fwd, left, up], -1)   # columns
    NOTE: this is NOT the full body frame; it ignores roll/pitch.
  - 10-dim state = [local_v(3) in R, target_v(3) in R, body_up(3) in WORLD, margin(1)]
      body_up = env.R[:, 2]  (TRUE body up / thrust direction in world frame,
                              requires full attitude — NOT constant [0,0,1])
      margin  = env.margin  (per-episode random scalar clearance in [0.1, 0.3] m,
                              NOT the camera min depth)
  - depth preprocessing (training):
      depth rendered 64x48 (meters) -> clamp(0.3, 24) -> x = 3/d - 0.6
      -> max_pool2d(4,4) -> 12x16  (max on inverse depth == min on raw depth,
      i.e. nearest obstacle per 4x4 cell)
  - action: model outputs 6 = [a_pred(3), v_pred(3)] expressed in frame R.
      a_pred_world = R @ a_pred ; v_pred_world = R @ v_pred
      net acceleration command (world) = (a_pred_world - v_pred_world - g)*thr + g
      with g = [0,0,-9.80665] and thr ~ 1 on real drone.
  - camera: R_cam = Ry(-cam_angle); rendered depth value = ray parameter t which
      equals z-depth in the camera frame (same semantic as RealSense z16 depth).

Deployment world frame: NEU (x=north, y=east, z=up), converted from PX4
LOCAL_POSITION_NED by negating z.  yaw is the PX4 NED heading.

This module deliberately provides NO empirical sign flips.  Any sign must be
proven by the coordinate tests in tests/test_coordinate_frames.py.
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Training constants (from upstream main_cuda.py / env_cuda.py / single_agent.args)
# ---------------------------------------------------------------------------
GRAVITY = 9.80665
G_STD = np.array([0.0, 0.0, -GRAVITY], dtype=np.float32)

DEPTH_MIN = 0.3      # clamp lower bound (m)
DEPTH_MAX = 24.0     # clamp upper bound (m)
TRAIN_FOV_X_HALF_TAN = 0.82   # single_agent.args --fov_x_half_tan
TRAIN_IMG_W = 64
TRAIN_IMG_H = 48
# fov_y_half_tan = fov_x_half_tan / W * H  (from render_cuda_kernel)
TRAIN_FOV_Y_HALF_TAN = TRAIN_FOV_X_HALF_TAN * TRAIN_IMG_H / TRAIN_IMG_W

# margin: per-episode uniform scalar in [0.1, 0.3] (env_cuda.reset())
MARGIN_TRAIN_LO, MARGIN_TRAIN_HI = 0.1, 0.3
MARGIN_DEFAULT = 0.2   # fixed deployment value inside training distribution

# D430 nominal optics (Intel datasheet: H:87deg, V:58deg, range 0.2-10m).
# Intrinsics are estimates derived from the nominal FOV; the board should
# read the real intrinsics from pyrealsense2 at runtime and pass them in.
D430_FX = 640.0 / (2.0 * np.tan(np.deg2rad(87.0) / 2.0))   # ~337.0
D430_FY = 480.0 / (2.0 * np.tan(np.deg2rad(58.0) / 2.0))   # ~433.0
D430_CX = 320.0
D430_CY = 240.0


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------
def yaw_only_frame(yaw: float) -> np.ndarray:
    """Training-identical yaw-only frame R (3x3, columns = [fwd, left, up]).

    Matches upstream:
      fwd  = [cos(yaw), sin(yaw), 0]
      left = cross(up, fwd) = [-sin(yaw), cos(yaw), 0]
      up   = [0,0,1]
    """
    c, s = float(np.cos(yaw)), float(np.sin(yaw))
    fwd = np.array([c, s, 0.0], dtype=np.float64)
    left = np.array([-s, c, 0.0], dtype=np.float64)
    up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return np.stack([fwd, left, up], axis=1)  # columns


def ned_to_body_dcm(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """NED->body DCM from Euler, v_body = R_nb @ v_ned.

    Textbook 3-2-1 aerospace convention (same as PX4 Dcmf):
      roll  positive = right roll (right arm down)
      pitch positive = nose up
      yaw   positive = turn right (clockwise from above)
      C_nb = [[cT cY,  cT sY, -sT],
              [sR sT cY - cR sY, sR sT sY + cR cY, sR cT],
              [cR sT cY + sR sY, cR sT sY - sR cY, cR cT]]
    Body axes in NED = rows of C_nb.  Verified against the standard
    Euler->quaternion composition and physical expectations in tests.
    """
    cr, sr = float(np.cos(roll)), float(np.sin(roll))
    cp, sp = float(np.cos(pitch)), float(np.sin(pitch))
    cy, sy = float(np.cos(yaw)), float(np.sin(yaw))
    return np.array([
        [cp * cy, cp * sy, -sp],
        [sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, sr * cp],
        [cr * sp * cy + sr * sy, cr * sp * sy - sr * cy, cr * cp],
    ], dtype=np.float64)


def dcm_from_quaternion(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """NED->body DCM from quaternion, matching the Euler DCM above.

    q = q_roll(roll/2) (x) * q_pitch(pitch/2) (y) * q_yaw(yaw/2) (z),
    Hamilton convention, v_body = R @ v_ned.
    """
    w, x, y, z = float(qw), float(qx), float(qy), float(qz)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)],
        [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)],
        [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def euler_to_quaternion(roll: float, pitch: float, yaw: float):
    """Standard Euler->quaternion for the 3-2-1 sequence (roll outermost)."""
    cr, sr = float(np.cos(roll / 2)), float(np.sin(roll / 2))
    cp, sp = float(np.cos(pitch / 2)), float(np.sin(pitch / 2))
    cy, sy = float(np.cos(yaw / 2)), float(np.sin(yaw / 2))
    return (cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy)


def _body_up_world_from_dcm(R_nb: np.ndarray) -> np.ndarray:
    """Body-up vector in world NEU from the NED->body DCM.

    Body z-axis (down) in NED = third row of R_nb; up = -down; NED->NEU flips z.
    """
    r = R_nb[2]  # body down axis in NED
    return np.array([-r[0], -r[1], r[2]], dtype=np.float64)


def body_up_world_neu(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """TRUE body-up (drone top / thrust direction) in world NEU frame.

    Matches upstream state slot env.R[:, 2] (body z-axis in world frame,
    z-up world).  Requires full roll/pitch/yaw — NOT just yaw.
    """
    return _body_up_world_from_dcm(ned_to_body_dcm(roll, pitch, yaw))


def body_up_world_from_quaternion(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """Body-up in world NEU from the MAVLink ATTITUDE quaternion."""
    return _body_up_world_from_dcm(dcm_from_quaternion(qw, qx, qy, qz))


# ---------------------------------------------------------------------------
# Depth preprocessing
# ---------------------------------------------------------------------------
def _masked_block_min(depth_m: np.ndarray, out_h: int, out_w: int,
                      invalid_fill: float = DEPTH_MAX) -> np.ndarray:
    """Conservative downsampling: each output pixel = min of valid depth over
    the block (nearest obstacle preserved).  Invalid pixels (<=0) are filled
    with a far value so they never dominate the min.
    """
    h, w = depth_m.shape
    bh, bw = h // out_h, w // out_w
    depth = depth_m.astype(np.float64).copy()
    depth[~(depth > 0)] = invalid_fill
    out = np.empty((out_h, out_w), dtype=np.float64)
    for i in range(out_h):
        for j in range(out_w):
            block = depth[i * bh:(i + 1) * bh, j * bw:(j + 1) * bw]
            out[i, j] = block.min()
    return out


def remap_to_training_fov(depth_m: np.ndarray,
                          fx: float = D430_FX, fy: float = D430_FY,
                          cx: float = D430_CX, cy: float = D430_CY,
                          out_w: int = TRAIN_IMG_W, out_h: int = TRAIN_IMG_H) -> np.ndarray:
    """Area-min remap: each training grid cell takes the MIN of all real pixels
    whose rays fall inside the cell (nearest obstacle in the cone wins).

    Training maps pixel (u,v) to ray direction with
      fu = (2*(u+0.5)/H - 1) * fov_y_half_tan
      fv = (2*(v+0.5)/W - 1) * fov_x_half_tan
    A pinhole camera maps the same angles to pixels (v-cx)/fx, (u-cy)/fy, so
    the training grid corresponds to a virtual image with
      v_real = fx * fv + cx ,  u_real = fy * fu + cy.
    Cells with no real rays inside are marked far (DEPTH_MAX).  Invalid real
    pixels are filled with a far value so they never dominate the min.
    """
    h, w = depth_m.shape
    # cell edges in training tan-space
    dv = 2.0 / out_w
    du = 2.0 / out_h
    vv0 = (np.arange(out_w, dtype=np.float64) * dv - 1.0) * TRAIN_FOV_X_HALF_TAN
    uu0 = (np.arange(out_h, dtype=np.float64) * du - 1.0) * TRAIN_FOV_Y_HALF_TAN
    vv1 = (np.arange(out_w, dtype=np.float64) * dv - 1.0 + dv) * TRAIN_FOV_X_HALF_TAN
    uu1 = (np.arange(out_h, dtype=np.float64) * du - 1.0 + du) * TRAIN_FOV_Y_HALF_TAN
    # real pixel ranges per cell (inclusive integer bounds)
    x0 = np.floor(fx * vv0 + cx).astype(int)      # (out_w,)
    x1 = np.ceil(fx * vv1 + cx).astype(int) - 1
    y0 = np.floor(fy * uu0 + cy).astype(int)      # (out_h,)
    y1 = np.ceil(fy * uu1 + cy).astype(int) - 1
    depth = depth_m.astype(np.float64)
    depth[~(depth > 0)] = DEPTH_MAX
    out = np.full((out_h, out_w), DEPTH_MAX, dtype=np.float64)
    for i in range(out_h):
        yi0, yi1 = max(y0[i], 0), min(y1[i], h - 1)
        if yi0 > yi1:
            continue
        for j in range(out_w):
            xj0, xj1 = max(x0[j], 0), min(x1[j], w - 1)
            if xj0 > xj1:
                continue
            out[i, j] = depth[yi0:yi1 + 1, xj0:xj1 + 1].min()
    return out

def preprocess_depth(depth_m: np.ndarray, mode: str = 'conservative',
                     fov_remap: bool = False, intrinsics: dict | None = None,
                     verbose: bool = False) -> dict:
    """Full training-consistent preprocessing.

    Args:
        depth_m: raw depth in meters, shape (H, W) (typically 480x640).
        mode: 'conservative' = masked block-min -> 64x48, then inverse depth,
              4x4 maxpool (matches training semantics: nearest obstacle wins).
              'legacy' = legacy INTER_AREA resize -> 64x48 (current web_vis).
        fov_remap: if True, first remap into the training FOV grid.
        intrinsics: optional dict(fx, fy, cx, cy) from pyrealsense2.

    Returns:
        dict with 'input' (1,1,12,16) model input, 'x64' (64,48) intermediate,
        plus stats: valid_ratio, depth_min, p1, p5, median, p95, near_ratio
        (fraction of valid pixels closer than 1 m).
    """
    d = depth_m.astype(np.float64)
    valid = d > 0
    valid_ratio = float(valid.mean())
    dv = d[valid]
    if dv.size:
        stats = {
            'valid_ratio': valid_ratio,
            'depth_min': float(dv.min()),
            'p1': float(np.percentile(dv, 1)),
            'p5': float(np.percentile(dv, 5)),
            'median': float(np.median(dv)),
            'p95': float(np.percentile(dv, 95)),
            'near_ratio': float((dv < 1.0).mean()),
        }
    else:
        stats = {'valid_ratio': 0.0, 'depth_min': None, 'p1': None,
                 'p5': None, 'median': None, 'p95': None, 'near_ratio': None}

    if fov_remap:
        intr = intrinsics or {}
        d = remap_to_training_fov(
            d, fx=intr.get('fx', D430_FX), fy=intr.get('fy', D430_FY),
            cx=intr.get('cx', D430_CX), cy=intr.get('cy', D430_CY))

    if mode == 'conservative':
        x64 = _masked_block_min(d, TRAIN_IMG_H, TRAIN_IMG_W)
    else:  # legacy INTER_AREA behaviour, kept only for comparison
        try:
            import cv2
            x64 = cv2.resize(d.astype(np.float32), (TRAIN_IMG_W, TRAIN_IMG_H),
                             interpolation=cv2.INTER_AREA).astype(np.float64)
        except ImportError:  # fallback: nearest
            x64 = d[::d.shape[0] // TRAIN_IMG_H, ::d.shape[1] // TRAIN_IMG_W]

    x64_clamped = np.clip(x64, DEPTH_MIN, DEPTH_MAX)
    x = 3.0 / x64_clamped - 0.6
    # 4x4 maxpool on inverse depth (max of 3/d == min of d)
    x_pooled = x.reshape(TRAIN_IMG_H // 4, 4, TRAIN_IMG_W // 4, 4).max(axis=(1, 3))
    return {
        'input': x_pooled.reshape(1, 1, 12, 16).astype(np.float32),
        'x64': x64,
        'stats': stats,
    }


# ---------------------------------------------------------------------------
# State construction
# ---------------------------------------------------------------------------
def build_state(local_v_world: np.ndarray, target_v_world: np.ndarray,
                body_up_world: np.ndarray, margin: float,
                R: np.ndarray | None = None, yaw: float | None = None) -> np.ndarray:
    """Build the exact 10-dim training state.

    [local_v(3) in R, target_v(3) in R, body_up(3) in WORLD, margin(1)]
    """
    if R is None:
        assert yaw is not None
        R = yaw_only_frame(yaw)
    local_v_body = R.T @ np.asarray(local_v_world, dtype=np.float64)
    target_v_body = R.T @ np.asarray(target_v_world, dtype=np.float64)
    up = np.asarray(body_up_world, dtype=np.float64)
    if up.ndim == 1:
        up = up / (np.linalg.norm(up) + 1e-12)
    return np.concatenate([local_v_body, target_v_body, up,
                           [float(margin)]]).astype(np.float32)


def clamp_target_velocity(target_v_world: np.ndarray, max_speed: float) -> np.ndarray:
    """Clamp target velocity magnitude to max_speed (training env.max_speed)."""
    n = float(np.linalg.norm(target_v_world))
    if n < 1e-6:
        return np.zeros(3, dtype=np.float64)
    return (np.asarray(target_v_world, dtype=np.float64) / n) * min(n, max_speed)


# ---------------------------------------------------------------------------
# Action decode
# ---------------------------------------------------------------------------
def decode_action(raw_action: np.ndarray, R: np.ndarray) -> dict:
    """Decode the 6-dim model output exactly as training.

    raw_action flat layout is INTERLEAVED [a_x, v_x, a_y, v_y, a_z, v_z]:
    upstream unpacks with act.reshape(B,3,-1) -> col0=(e0,e2,e4)=a_pred,
    col1=(e1,e3,e5)=v_pred, both expressed in frame R.
    net_accel_world = (R @ a_pred - R @ v_pred - g) * 1 + g
                    = R @ (a_pred - v_pred)
    Returns a_pred/v_pred/net_accel in world (NEU) and in body frame R.
    """
    act = np.asarray(raw_action, dtype=np.float64).reshape(3, 2)
    a_body = act[:, 0]
    v_body = act[:, 1]
    a_world = R @ a_body
    v_world = R @ v_body
    net_world = a_world - v_world  # == (a_pred - v_pred - g) + g for thr=1
    return {
        'accel_body': a_body.astype(np.float32),
        'accel_world': a_world.astype(np.float32),
        'vpred_body': v_body.astype(np.float32),
        'vpred_world': v_world.astype(np.float32),
        'net_accel_world': net_world.astype(np.float32),
    }


def legacy_decode_action(raw_action: np.ndarray, yaw: float) -> dict:
    """Legacy decode used by current web_vis.py (sign flips + no vpred),
    kept ONLY for A/B comparison in the offline benchmark."""
    R = yaw_only_frame(yaw)
    act = np.asarray(raw_action, dtype=np.float64).reshape(3, 2)
    a_body = act[:, 0].copy()
    v_body = act[:, 1].copy()
    a_body[0] *= -1.0
    a_body[1] *= -1.0
    v_body[0] *= -1.0
    v_body[1] *= -1.0
    return {
        'accel_body': a_body.astype(np.float32),
        'accel_world': (R @ a_body).astype(np.float32),
        'vpred_body': v_body.astype(np.float32),
        'vpred_world': (R @ v_body).astype(np.float32),
        'net_accel_world': (R @ a_body).astype(np.float32),
    }
