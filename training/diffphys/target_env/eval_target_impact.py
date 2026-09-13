"""Evaluate trained target-impact policy in DiffPhys environment.

Runs N episodes, records:
- target_hits / target_hit_rate
- wrong_collisions / wrong_collision_rate
- timeouts / timeout_rate
- impact_velocity (mean/std)
- impact_angle (mean/p95)
- time_to_target (mean)
- center_hits / center_hit_rate

Usage: python eval_target_impact.py --checkpoint results/checkpoints/target_impact_final.pth --episodes 1000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

UPSTREAM = Path(__file__).resolve().parent.parent / "upstream"
sys.path.insert(0, str(UPSTREAM))

from env_cuda import Env  # noqa: E402
from model import Model  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--batch_size", type=int, default=256)
    parser.add_argument("--timesteps", type=int, default=200)
    parser.add_argument("--armor_x", type=float, default=3.08)
    parser.add_argument("--armor_y", type=float, default=3.84)
    parser.add_argument("--armor_z", type=float, default=1.5)
    parser.add_argument("--hit_radius", type=float, default=0.3)
    parser.add_argument("--center_radius", type=float, default=0.1)
    parser.add_argument("--output", default="results/target_impact_eval.json")
    parser.add_argument("--fov_x_half_tan", type=float, default=0.82)
    parser.add_argument("--cam_angle", type=int, default=10)
    parser.add_argument("--speed_mtp", type=float, default=2.0)
    return parser.parse_args()


@torch.no_grad()
def evaluate(args):
    device = torch.device("cuda")
    armor_pos = torch.tensor([args.armor_x, args.armor_y, args.armor_z], device=device)

    env = Env(
        args.batch_size, 64, 48, 0.4, device,
        fov_x_half_tan=args.fov_x_half_tan, single=True,
        ground_voxels=True, speed_mtp=args.speed_mtp,
        random_rotation=True, cam_angle=args.cam_angle,
    )

    model = Model(10, 6).to(device)
    state_dict = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(state_dict, strict=False)
    model.eval()

    all_results = []
    episodes_done = 0

    while episodes_done < args.episodes:
        env.reset()
        env.p_target = armor_pos[None, :].repeat(args.batch_size, 1)
        model.reset()
        h = None
        act_buffer = [env.act] * 2

        episode_hits = torch.zeros(args.batch_size, device=device)
        episode_wrong = torch.zeros(args.batch_size, device=device)
        episode_timeout = torch.ones(args.batch_size, device=device)
        episode_impact_vel = torch.zeros(args.batch_size, device=device)
        episode_impact_angle = torch.zeros(args.batch_size, device=device)
        episode_time = torch.full((args.batch_size,), float(args.timesteps), device=device)
        episode_center = torch.zeros(args.batch_size, device=device)

        for t in range(args.timesteps):
            ctl_dt = 1 / 15
            depth, _ = env.render(ctl_dt)
            target_v_raw = env.p_target - env.p
            env.run(act_buffer[-1], ctl_dt, target_v_raw)

            R = env.R
            fwd = env.R[:, :, 0].clone()
            up = torch.zeros_like(fwd)
            fwd[:, 2] = 0
            up[:, 2] = 1
            fwd = F.normalize(fwd, 2, -1)
            R = torch.stack([fwd, torch.cross(up, fwd), up], -1)

            target_v_norm = torch.norm(target_v_raw, 2, -1, keepdim=True)
            target_v = target_v_raw / (target_v_norm + 1e-8) * torch.minimum(target_v_norm, env.max_speed)
            local_v = torch.squeeze(env.v[:, None] @ R, 1)
            state = torch.cat([
                local_v,
                torch.squeeze(target_v[:, None] @ R, 1),
                env.R[:, 2],
                env.margin[:, None],
            ], -1)

            x = 3 / depth.clamp(0.3, 24) - 0.6
            x = F.max_pool2d(x[:, None], 4, 4)
            act, _, h = model(x, state, h)

            a_pred, v_pred, *_ = (R @ act.reshape(args.batch_size, 3, -1)).unbind(-1)
            act = (a_pred - v_pred - env.g_std) * env.thr_est_error[:, None] + env.g_std
            act_buffer.append(act)

            # Check hits
            dist = torch.norm(env.p - env.p_target, 2, -1)
            speed = torch.norm(env.v, 2, -1)
            v_dir = env.v / (speed[:, None] + 1e-8)
            t_dir = (env.p_target - env.p) / (dist[:, None] + 1e-8)
            angle = torch.acos((v_dir * t_dir).sum(-1).clamp(-1, 1)) * 180 / np.pi

            newly_hit = (dist < args.hit_radius) & (episode_hits == 0)
            episode_hits[newly_hit] = 1
            episode_impact_vel[newly_hit] = speed[newly_hit]
            episode_impact_angle[newly_hit] = angle[newly_hit]
            episode_time[newly_hit] = t
            episode_center[newly_hit & (dist < args.center_radius)] = 1
            episode_timeout[newly_hit] = 0

            # Check wrong collisions (very close to obstacles)
            vec_to_pt = env.find_vec_to_nearest_pt()
            nearest_dist = torch.norm(vec_to_pt, 2, -1) - env.margin
            newly_wrong = (nearest_dist < 0.05) & (episode_wrong == 0) & (episode_hits == 0)
            episode_wrong[newly_wrong] = 1

        n = min(args.batch_size, args.episodes - episodes_done)
        for i in range(n):
            all_results.append({
                "target_hit": bool(episode_hits[i].item()),
                "center_hit": bool(episode_center[i].item()),
                "wrong_collision": bool(episode_wrong[i].item()),
                "timeout": bool(episode_timeout[i].item()),
                "impact_velocity": float(episode_impact_vel[i].item()),
                "impact_angle": float(episode_impact_angle[i].item()),
                "time_to_target": float(episode_time[i].item()),
            })
        episodes_done += n

    # Aggregate
    hits = [r for r in all_results if r["target_hit"]]
    metrics = {
        "episodes": len(all_results),
        "target_hits": len(hits),
        "target_hit_rate": len(hits) / len(all_results),
        "center_hits": sum(r["center_hit"] for r in all_results),
        "center_hit_rate": sum(r["center_hit"] for r in all_results) / len(all_results),
        "wrong_collisions": sum(r["wrong_collision"] for r in all_results),
        "wrong_collision_rate": sum(r["wrong_collision"] for r in all_results) / len(all_results),
        "timeouts": sum(r["timeout"] for r in all_results),
        "timeout_rate": sum(r["timeout"] for r in all_results) / len(all_results),
        "impact_velocity_mean": float(np.mean([r["impact_velocity"] for r in hits])) if hits else 0.0,
        "impact_velocity_std": float(np.std([r["impact_velocity"] for r in hits])) if hits else 0.0,
        "impact_angle_mean": float(np.mean([r["impact_angle"] for r in hits])) if hits else 0.0,
        "impact_angle_p95": float(np.percentile([r["impact_angle"] for r in hits], 95)) if hits else 0.0,
        "time_to_target_mean": float(np.mean([r["time_to_target"] for r in hits])) if hits else 0.0,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(metrics, f, indent=2)

    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    args = parse_args()
    evaluate(args)
