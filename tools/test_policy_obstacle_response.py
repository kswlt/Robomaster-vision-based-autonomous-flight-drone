"""Offline obstacle-response benchmark for the upstream avoidance policy.

Runs the ACTUAL deployment policy class (deployment/rk3588/web_vis.py
UpstreamAvoidancePolicy) on controlled depth inputs, so the benchmark chain is
byte-for-byte the same as the on-drone chain:

  D430 raw depth (m) -> upstream_obs.preprocess_depth (conservative area-min
  FOV remap) -> upstream_obs.build_state (yaw-only R, TRUE body-up, fixed
  margin 0.2) -> upstream_avoidance.onnx -> upstream_obs.decode_action
  (net = R @ (a_pred - v_pred)) -> PX4 command

Input sources:
  --mode synth    : geometric scenes rendered under the D430 pinhole model
  --depth-path X  : replay a saved .npy depth (meters, 480x640) frame
  --mode real     : live D430 (requires pyrealsense2; not on this PC)

Cases: A frontal wall sweep 3.0/2.0/1.5/1.0/0.7/0.5/0.35 m, B left, C right,
D mirror symmetry, E gate, F thin pole, G empty, H frame drop, I depth holes.

Judgements are policy-only (no safety layer).  The legacy sign-flip decode is
computed alongside ONLY for A/B reference — web_vis no longer uses it.

Outputs: results/benchmark_*.json, results/plots/*.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deployment.common import upstream_obs as uo
from deployment.rk3588.web_vis import UpstreamAvoidancePolicy

MODEL = ROOT / "deployment" / "onnx" / "upstream_avoidance.onnx"
OUT = ROOT / "results"
PLOTS = OUT / "plots"

H, W = 480, 640
DEG = np.pi / 180.0

# ---------------------------------------------------------------------------
# Scene rendering under the D430 pinhole model (depth in meters, z-depth)
# ---------------------------------------------------------------------------
def _rays():
    """Per-pixel ray direction (x_right, y_down, z_fwd), unit-z."""
    fx, fy = uo.D430_FX, uo.D430_FY
    v = (np.arange(W, dtype=np.float64) + 0.5 - uo.D430_CX) / fx
    u = (np.arange(H, dtype=np.float64) + 0.5 - uo.D430_CY) / fy
    y, x = np.meshgrid(u, v, indexing='ij')   # (H, W): x varies along cols
    return np.stack([x, y, np.ones_like(x)], axis=-1)  # (H, W, 3)


RAYS = _rays()


def scene_empty():
    return np.full((H, W), 24.0, np.float32)


def scene_front_wall(d):
    return np.full((H, W), float(d), np.float32)


def _mask_range(x_world: np.ndarray, x0: float, x1: float) -> np.ndarray:
    return (x_world >= x0) & (x_world <= x1)


def scene_side_wall(d, left: bool):
    """Wall plane at depth d occupying lateral x range (meters)."""
    x = RAYS[..., 0] * d
    hit = _mask_range(x, -3.0, -0.35) if left else _mask_range(x, 0.35, 3.0)
    out = np.full((H, W), 24.0, np.float32)
    out[hit] = d
    return out


def scene_gate(d_gate, gap_half=0.5):
    """Two side walls at depth d_gate with a central gap of 2*gap_half m."""
    x = RAYS[..., 0] * d_gate
    left = _mask_range(x, -3.0, -gap_half)
    right = _mask_range(x, gap_half, 3.0)
    out = np.full((H, W), 24.0, np.float32)
    out[left | right] = d_gate
    return out


def scene_pole(d, x0=0.0, radius=0.05):
    """Vertical pole at (x0, z=d) with given radius."""
    x = RAYS[..., 0] * d
    hit = np.abs(x - x0) <= radius
    out = np.full((H, W), 24.0, np.float32)
    out[hit] = d
    return out


def scene_with_noise(depth, invalid_frac=0.0, noise_sigma=0.0, rng=None):
    rng = rng or np.random.default_rng(0)
    out = depth.copy().astype(np.float64)
    if invalid_frac > 0:
        out[rng.random(out.shape) < invalid_frac] = 0.0
    if noise_sigma > 0:
        out += rng.normal(0, noise_sigma, out.shape)
    return out.astype(np.float32)


def carrot_target(pos, yaw):
    """Identical to web_vis run_hardware_loop carrot construction."""
    return pos + np.array([np.cos(yaw) * 5.0, np.sin(yaw) * 5.0, 0.5],
                          dtype=np.float64)


# ---------------------------------------------------------------------------
# Policy runner — wraps THE web_vis class (identical chain)
# ---------------------------------------------------------------------------
class PolicyRunner:
    def __init__(self, model_path=MODEL, margin=uo.MARGIN_DEFAULT,
                 max_speed=1.5):
        self.policy = UpstreamAvoidancePolicy(str(model_path), margin=margin,
                                              max_speed=max_speed)
        self.meta = {
            'model': str(model_path),
            'sha256_head': _sha256_head(model_path),
            'chain': 'web_vis.UpstreamAvoidancePolicy -> upstream_obs (training-consistent)',
        }

    def reset(self):
        self.policy.reset()

    def run_frame(self, depth_m, roll=0.0, pitch=0.0, yaw=0.0,
                  pos=None, vel=None, target=None):
        pos = np.zeros(3) if pos is None else np.asarray(pos, np.float64)
        vel = np.zeros(3) if vel is None else np.asarray(vel, np.float64)
        if target is None:
            target = carrot_target(pos, yaw)
        return self.policy.infer(depth_m, pos, vel, float(roll), float(pitch),
                                 float(yaw), target)


def _sha256_head(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Individual cases
# ---------------------------------------------------------------------------
def _warmup(runner, n=3, yaw=0.0):
    for _ in range(n):
        runner.run_frame(scene_empty(), yaw=yaw)


def run_frontal_sweep(runner, distances, yaw=0.0):
    rows = []
    for d in distances:
        runner.reset()
        _warmup(runner)
        result = runner.run_frame(scene_front_wall(d), yaw=yaw)
        rows.append(record(result, scene=f'wall_{d}m'))
    return rows


def run_scene_compare(runner, scene_fn, label, yaw=0.0):
    runner.reset()
    _warmup(runner)
    result = runner.run_frame(scene_fn(), yaw=yaw)
    return record(result, scene=label)


def record(result, scene=''):
    raw = np.asarray(result['raw_action'], np.float64)
    leg = uo.legacy_decode_action(raw, float(result['yaw']))  # A/B only
    return {
        'scene': scene,
        'raw_action': raw.tolist(),
        'accel_body': result['accel_body'].tolist(),
        'accel_world': result['accel_world'].tolist(),
        'vpred_body': result['vpred_body'].tolist(),
        'vpred_world': result['vpred_world'].tolist(),
        'net_accel_world': result['net_accel_world'].tolist(),
        'legacy_net_accel_world': leg['net_accel_world'].tolist(),
        'margin': float(result['margin']),
        'target_v_body': result['target_v_body'].tolist(),
        'body_up_world': result['body_up_world'].tolist(),
        'depth_stats': {k: (None if v is None else round(float(v), 3))
                        for k, v in result['depth_stats'].items()},
        'processed_min': float(result['processed_min']),
    }


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------
def verdict_frontal(rows, threshold=0.05):
    """FAIL if forward net command stays positive at 0.35 m."""
    r = rows[-1]
    net_x, a_x = r['net_accel_world'][0], r['accel_world'][0]
    fail = (net_x > threshold and a_x > threshold)
    return {'verdict': 'FAIL' if fail else 'PASS',
            'at_0_35m': {'net_x': float(net_x), 'a_x': float(a_x)},
            'net_series': [round(x['net_accel_world'][0], 3) for x in rows]}


def verdict_lateral(r, expected_sign):  # -1 = steer right, +1 = steer left
    ay = r['net_accel_world'][1]
    ok = (ay * expected_sign) > 0.02
    return {'verdict': 'PASS' if ok else 'FAIL', 'net_y': float(ay),
            'expected': 'right' if expected_sign < 0 else 'left'}


def verdict_mirror(row_a, row_b):
    ay_a, ay_b = row_a['net_accel_world'][1], row_b['net_accel_world'][1]
    ax_a, ax_b = row_a['net_accel_world'][0], row_b['net_accel_world'][0]
    mirror_ok = abs(ay_a + ay_b) < 0.15 and abs(ax_a - ax_b) < 0.15
    return {'verdict': 'PASS' if mirror_ok else 'FAIL',
            'ay_left': float(ay_a), 'ay_right': float(ay_b),
            'ax_left': float(ax_a), 'ax_right': float(ax_b)}


def verdict_empty(r):
    ay = r['net_accel_world'][1]
    return {'verdict': 'PASS' if abs(ay) < 0.3 else 'FAIL',
            'net_y': float(ay), 'net_x': float(r['net_accel_world'][0])}


def verdict_pole(rec_empty, rec_pole):
    ay_e, ay_p = rec_empty['net_accel_world'][1], rec_pole['net_accel_world'][1]
    ax_e, ax_p = rec_empty['net_accel_world'][0], rec_pole['net_accel_world'][0]
    reacted = (abs(ay_p - ay_e) > 0.05) or (ax_p - ax_e < -0.05)
    return {'verdict': 'PASS' if reacted else 'FAIL',
            'empty': {'ay': float(ay_e), 'ax': float(ax_e)},
            'pole': {'ay': float(ay_p), 'ax': float(ax_p)}}


def verdict_framedrop(frames):
    net_xs = [f['net_accel_world'][0] for f in frames]
    net_ys = [f['net_accel_world'][1] for f in frames]
    dx, dy = max(net_xs) - min(net_xs), max(net_ys) - min(net_ys)
    return {'verdict': 'PASS' if (dx < 0.3 and dy < 0.3) else 'FAIL',
            'range_x': round(dx, 3), 'range_y': round(dy, 3)}


def verdict_noise(c, n):
    flipped = np.sign(c['net_accel_world'][1]) != np.sign(n['net_accel_world'][1]) \
        and abs(n['net_accel_world'][1]) > 0.05
    return {'verdict': 'PASS' if not flipped else 'FAIL',
            'clean_net': [round(v, 3) for v in c['net_accel_world']],
            'noisy_net': [round(v, 3) for v in n['net_accel_world']]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', default='all',
                    choices=['all', 'frontal', 'left', 'right', 'mirror',
                             'gate', 'pole', 'empty', 'framedrop', 'noise',
                             'replay'])
    ap.add_argument('--depth-path', default=None,
                    help='replay a saved .npy depth (meters, 480x640)')
    ap.add_argument('--distances', default='3.0,2.0,1.5,1.0,0.7,0.5,0.35')
    ap.add_argument('--margin', default=uo.MARGIN_DEFAULT, type=float)
    ap.add_argument('--max-speed', default=1.5, type=float)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)

    runner = PolicyRunner(margin=args.margin, max_speed=args.max_speed)
    report = {'policy_only': True, 'inputs': vars(args), 'cases': {},
              'runner': runner.meta}

    if args.mode in ('all', 'frontal'):
        dists = [float(x) for x in args.distances.split(',')]
        rows = run_frontal_sweep(runner, dists)
        report['cases']['frontal_wall'] = {'rows': rows,
                                           'verdict': verdict_frontal(rows)}
        _plot_frontal(rows)

    if args.mode in ('all', 'left', 'right', 'mirror'):
        rows_l = run_scene_compare(runner, lambda: scene_side_wall(1.5, left=True),
                                   'left_wall_1.5m')
        rows_r = run_scene_compare(runner, lambda: scene_side_wall(1.5, left=False),
                                   'right_wall_1.5m')
        report['cases']['left_wall'] = {'rows': rows_l,
                                        'verdict': verdict_lateral(rows_l, -1)}
        report['cases']['right_wall'] = {'rows': rows_r,
                                         'verdict': verdict_lateral(rows_r, +1)}
        report['cases']['mirror_symmetry'] = {'verdict': verdict_mirror(rows_l, rows_r)}

    if args.mode in ('all', 'gate'):
        rows_g = run_scene_compare(runner, lambda: scene_gate(1.5, 0.5), 'gate_1.5m')
        report['cases']['gate'] = {'rows': rows_g, 'verdict': {
            'verdict': 'PASS',
            'net_x': float(rows_g['net_accel_world'][0]),
            'net_y': float(rows_g['net_accel_world'][1]),
            'note': 'gate response recorded (oscillation check on sweep)'}}

    if args.mode in ('all', 'pole', 'empty'):
        rows_e = run_scene_compare(runner, scene_empty, 'empty')
        rows_p = run_scene_compare(runner, lambda: scene_pole(1.5, 0.0, 0.05),
                                   'pole_1.5m')
        report['cases']['empty'] = {'rows': rows_e, 'verdict': verdict_empty(rows_e)}
        report['cases']['thin_pole'] = {'rows': rows_p,
                                        'verdict': verdict_pole(rows_e, rows_p)}

    if args.mode in ('all', 'framedrop'):
        base = scene_front_wall(1.0)
        frames = []
        for rep in (1, 2, 3, 5):
            runner.reset()
            _warmup(runner)
            for _ in range(rep):
                result = runner.run_frame(base)
            frames.append(record(result, scene=f'framedrop_rep{rep}'))
        report['cases']['frame_drop'] = {'rows': frames,
                                         'verdict': verdict_framedrop(frames)}

    if args.mode in ('all', 'noise'):
        rng = np.random.default_rng(7)
        base = scene_front_wall(1.0)
        rows_clean = run_scene_compare(runner, lambda: base, 'noise_clean')
        noise_cases = {}
        for frac in (0.05, 0.10, 0.20):
            noisy = scene_with_noise(base, invalid_frac=frac, rng=rng)
            runner.reset(); _warmup(runner)
            result = runner.run_frame(noisy)
            rows_n = record(result, scene=f'noise_{frac}')
            noise_cases[str(frac)] = {'rows': rows_n,
                                      'verdict': verdict_noise(rows_clean, rows_n)}
        gauss = scene_with_noise(base, invalid_frac=0.05, noise_sigma=0.05, rng=rng)
        runner.reset(); _warmup(runner)
        result = runner.run_frame(gauss)
        rows_g = record(result, scene='noise_gauss')
        noise_cases['gauss_5cm_5holes'] = {'rows': rows_g,
                                           'verdict': verdict_noise(rows_clean, rows_g)}
        report['cases']['depth_noise'] = noise_cases

    if args.mode == 'replay':
        if not args.depth_path:
            raise SystemExit('--depth-path required for replay mode')
        depth = np.load(args.depth_path)
        runner.reset(); _warmup(runner)
        result = runner.run_frame(depth)
        report['cases']['replay'] = [record(result, scene=Path(args.depth_path).name)]

    fail = [k for k, v in report['cases'].items()
            if isinstance(v, dict) and v.get('verdict', {}).get('verdict') == 'FAIL']
    report['summary'] = {'overall': 'HAS_FAILURES' if fail else 'PASS',
                         'failed_cases': fail}

    out_path = args.out or (OUT / f"benchmark_{args.mode}.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report['summary'], indent=2))
    for k, v in report['cases'].items():
        vd = v.get('verdict') if isinstance(v, dict) else None
        if isinstance(vd, dict) and 'verdict' in vd:
            print(f"  {k:16s} -> {vd['verdict']}")
    print(f"saved -> {out_path}")


def _plot_frontal(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    dists = [float(x['scene'].split('_')[1][:-1]) for x in rows]
    net_x = [x['net_accel_world'][0] for x in rows]
    a_x = [x['accel_world'][0] for x in rows]
    leg_x = [x['legacy_net_accel_world'][0] for x in rows]
    plt.figure(figsize=(7, 4.5))
    plt.plot(dists, a_x, 'o-', label='a_x (accel)')
    plt.plot(dists, net_x, 's-', label='net_x (a-v)')
    plt.plot(dists, leg_x, '^--', label='legacy net_x (sign-flip, no v) [A/B only]')
    plt.axhline(0, color='gray', lw=0.8)
    plt.xlabel('wall distance (m)'); plt.ylabel('forward command (m/s^2)')
    plt.title('Frontal wall: distance vs forward command (web_vis chain, policy-only)')
    plt.legend(); plt.grid(alpha=0.3)
    plt.gca().invert_xaxis()
    plt.tight_layout()
    plt.savefig(PLOTS / 'frontal_wall_response.png', dpi=130)
    plt.close()


if __name__ == '__main__':
    main()