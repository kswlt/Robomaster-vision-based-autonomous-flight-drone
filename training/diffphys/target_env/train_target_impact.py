"""Target-Impact Policy Training (DiffPhysDrone modified for armor plate impact).

This script modifies the original DiffPhysDrone training objective:
- Original: velocity tracking + obstacle avoidance (fly through forest)
- Modified: fly TO a fixed target (armor plate) and HIT it, while avoiding
  all other obstacles. Target collision = SUCCESS, other collision = FAILURE.

Key changes from main_cuda.py:
1. Fixed armor target position (p_end overridden to armor location)
2. Loss includes: goal approach, target-hit reward, wrong-collision penalty,
   impact velocity reward, impact angle reward, control smoothness
3. Target is NEVER in obstacle avoidance loss (it's a position, not an obstacle)
4. Checkpoint saved and reloadable
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from tqdm import tqdm

# Add upstream to path
UPSTREAM = Path(__file__).resolve().parent.parent / "upstream"
sys.path.insert(0, str(UPSTREAM))

from env_cuda import Env  # noqa: E402
from model import Model  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Target-impact policy training")
    parser.add_argument("--resume", default=None)
    parser.add_argument("--batch_size", type=int, default=128)
    parser.add_argument("--num_iters", type=int, default=30000)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--grad_decay", type=float, default=0.4)
    parser.add_argument("--timesteps", type=int, default=150)
    parser.add_argument("--fov_x_half_tan", type=float, default=0.82)
    parser.add_argument("--cam_angle", type=int, default=10)
    parser.add_argument("--speed_mtp", type=float, default=2.0)

    # Armor target position (world frame, meters)
    # Default: central structure armor plate location from RMUC arena analysis
    parser.add_argument("--armor_x", type=float, default=3.08)
    parser.add_argument("--armor_y", type=float, default=3.84)
    parser.add_argument("--armor_z", type=float, default=1.5)

    # Loss weights
    parser.add_argument("--coef_goal", type=float, default=2.0, help="distance to target")
    parser.add_argument("--coef_target_hit", type=float, default=10.0, help="reward for being near target")
    parser.add_argument("--coef_wrong_collision", type=float, default=5.0, help="penalty for obstacle collision")
    parser.add_argument("--coef_impact_vel", type=float, default=1.0, help="reward for impact velocity in range")
    parser.add_argument("--coef_impact_angle", type=float, default=2.0, help="reward for heading toward target")
    parser.add_argument("--coef_d_acc", type=float, default=0.01, help="control acceleration regularization")
    parser.add_argument("--coef_d_jerk", type=float, default=0.001, help="control jerk regularization")
    parser.add_argument("--coef_v_pred", type=float, default=2.0, help="velocity prediction loss")

    # Impact parameters
    parser.add_argument("--hit_radius", type=float, default=0.3, help="distance threshold for target hit (m)")
    parser.add_argument("--min_impact_speed", type=float, default=2.0, help="minimum impact speed (m/s)")
    parser.add_argument("--max_impact_speed", type=float, default=10.0, help="maximum impact speed (m/s)")

    # Curriculum
    parser.add_argument("--curriculum", action="store_true", default=True, help="enable curriculum learning")
    parser.add_argument("--checkpoint_dir", default="results/checkpoints")
    parser.add_argument("--log_interval", type=int, default=25)
    parser.add_argument("--save_interval", type=int, default=2000)

    return parser.parse_args()


def smooth_dict(ori_dict, scaler_q):
    for k, v in ori_dict.items():
        scaler_q[k].append(float(v))


def barrier(x, v_to_pt):
    return (v_to_pt * (1 - x).relu().pow(2)).mean()


def main():
    args = parse_args()
    device = torch.device("cuda")

    os.makedirs(args.checkpoint_dir, exist_ok=True)

    # Armor target position
    armor_pos = torch.tensor([args.armor_x, args.armor_y, args.armor_z], device=device)

    # Environment (single agent mode for target impact)
    env = Env(
        args.batch_size, 64, 48, args.grad_decay, device,
        fov_x_half_tan=args.fov_x_half_tan, single=True,
        ground_voxels=True, speed_mtp=args.speed_mtp,
        random_rotation=True, cam_angle=args.cam_angle,
    )

    # Model (with odometry: state dim = 10, action dim = 6)
    model = Model(10, 6).to(device)

    if args.resume:
        state_dict = torch.load(args.resume, map_location=device)
        model.load_state_dict(state_dict, strict=False)
        print(f"Resumed from {args.resume}")

    optim = AdamW(model.parameters(), args.lr)
    sched = CosineAnnealingLR(optim, args.num_iters, args.lr * 0.01)

    ctl_dt = 1 / 15
    scaler_q = defaultdict(list)
    B = args.batch_size

    pbar = tqdm(range(args.num_iters), ncols=100)
    for i in pbar:
        env.reset()
        # Override p_end to fixed armor target (with small randomization for curriculum)
        if args.curriculum and i < 5000:
            # Stage 1: no randomization, fixed target
            env.p_target = armor_pos[None, :].repeat(B, 1)
        else:
            # Stage 2+: small target position randomization
            rand_offset = torch.randn(B, 3, device=device) * 0.5
            env.p_target = armor_pos[None, :] + rand_offset

        model.reset()
        p_history = []
        v_history = []
        act_history = []
        v_preds = []
        h = None
        act_lag = 1
        act_buffer = [env.act] * (act_lag + 1)

        for t in range(args.timesteps):
            ctl_dt = torch.normal(torch.tensor(1 / 15), torch.tensor(0.1 / 15)).item()
            depth, flow = env.render(ctl_dt)
            p_history.append(env.p)
            target_v_raw = env.p_target - env.p.detach()

            env.run(act_buffer[t], ctl_dt, target_v_raw)

            R = env.R
            fwd = env.R[:, :, 0].clone()
            up = torch.zeros_like(fwd)
            fwd[:, 2] = 0
            up[:, 2] = 1
            fwd = F.normalize(fwd, 2, -1)
            R = torch.stack([fwd, torch.cross(up, fwd), up], -1)

            target_v_norm = torch.norm(target_v_raw, 2, -1, keepdim=True)
            target_v_unit = target_v_raw / (target_v_norm + 1e-8)
            target_v = target_v_unit * torch.minimum(target_v_norm, env.max_speed)
            local_v = torch.squeeze(env.v[:, None] @ R, 1)
            state = torch.cat([
                local_v,
                torch.squeeze(target_v[:, None] @ R, 1),
                env.R[:, 2],
                env.margin[:, None],
            ], -1)

            # Depth normalization (matching upstream)
            x = 3 / depth.clamp_(0.3, 24) - 0.6 + torch.randn_like(depth) * 0.02
            x = F.max_pool2d(x[:, None], 4, 4)
            act, values, h = model(x, state, h)

            a_pred, v_pred, *_ = (R @ act.reshape(B, 3, -1)).unbind(-1)
            v_preds.append(v_pred)
            act = (a_pred - v_pred - env.g_std) * env.thr_est_error[:, None] + env.g_std
            act_buffer.append(act)
            v_history.append(env.v)
            act_history.append(act)

        # --- Compute losses ---
        p_history = torch.stack(p_history)  # (T, B, 3)
        v_history = torch.stack(v_history)
        act_history = torch.stack(act_history)
        v_preds = torch.stack(v_preds)

        # Distance to target
        dist_to_target = torch.norm(p_history - env.p_target[None, :, :], 2, -1)  # (T, B)

        # 1. Goal approach loss (minimize final distance)
        loss_goal = dist_to_target[-1].mean()

        # 2. Target hit reward (softplus of negative distance near end)
        # Reward increases as drone gets close to target
        hit_reward = F.softplus(-dist_to_target[-1] * 5).mean()
        loss_target_hit = -hit_reward  # minimize negative reward

        # 3. Wrong collision penalty (obstacle avoidance)
        vec_to_pt = env.find_vec_to_nearest_pt()
        # Note: find_vec_to_nearest_pt uses current p, need history
        # Use the last position's nearest obstacle
        nearest_dist = torch.norm(vec_to_pt, 2, -1) - env.margin
        with torch.no_grad():
            v_to_obstacle = (-torch.diff(nearest_dist[None, :], 1, 1) * 135).clamp_min(1)
        # Collision penalty: softplus when very close to obstacles
        loss_wrong_collision = F.softplus(nearest_dist * -32).mean()

        # 4. Impact velocity reward (speed in target range when near target)
        final_speed = torch.norm(v_history[-1], 2, -1)
        near_target = (dist_to_target[-1] < args.hit_radius * 3).float()
        # Reward speed in [min, max] range
        speed_in_range = (final_speed - args.min_impact_speed).clamp_min(0) * \
                         (args.max_impact_speed - final_speed).clamp_min(0)
        loss_impact_vel = -(speed_in_range * near_target).mean()

        # 5. Impact angle reward (velocity direction toward target)
        final_v_dir = v_history[-1] / (final_speed[:, None] + 1e-8)
        target_dir = (env.p_target - p_history[-1]) / (dist_to_target[-1][:, None] + 1e-8)
        alignment = (final_v_dir * target_dir).sum(-1)  # cos(angle), 1 = head-on
        loss_impact_angle = -(alignment * near_target).mean()

        # 6. Control regularization
        jerk = act_history.diff(1, 0).mul(15)
        loss_d_acc = act_history.pow(2).sum(-1).mean()
        loss_d_jerk = jerk.pow(2).sum(-1).mean()

        # 7. Velocity prediction loss
        loss_v_pred = F.mse_loss(v_preds, v_history.detach())

        # Total loss
        loss = (
            args.coef_goal * loss_goal
            + args.coef_target_hit * loss_target_hit
            + args.coef_wrong_collision * loss_wrong_collision
            + args.coef_impact_vel * loss_impact_vel
            + args.coef_impact_angle * loss_impact_angle
            + args.coef_d_acc * loss_d_acc
            + args.coef_d_jerk * loss_d_jerk
            + args.coef_v_pred * loss_v_pred
        )

        if torch.isnan(loss):
            print("loss is nan, skipping iteration")
            continue

        pbar.set_description_str(f"loss: {loss:.3f} dist: {loss_goal:.3f}")
        optim.zero_grad()
        loss.backward()
        optim.step()
        sched.step()

        # Metrics
        with torch.no_grad():
            hits = (dist_to_target[-1] < args.hit_radius).sum().item()
            hit_rate = hits / B
            avg_final_dist = dist_to_target[-1].mean().item()
            avg_final_speed = final_speed.mean().item()
            smooth_dict({
                'loss': loss,
                'loss_goal': loss_goal,
                'loss_target_hit': loss_target_hit,
                'loss_wrong_collision': loss_wrong_collision,
                'loss_impact_vel': loss_impact_vel,
                'loss_impact_angle': loss_impact_angle,
                'loss_d_acc': loss_d_acc,
                'loss_d_jerk': loss_d_jerk,
                'loss_v_pred': loss_v_pred,
                'hit_rate': hit_rate,
                'avg_final_dist': avg_final_dist,
                'avg_final_speed': avg_final_speed,
            }, scaler_q)

        if (i + 1) % args.log_interval == 0:
            for k, v in scaler_q.items():
                print(f"  {k}: {sum(v)/len(v):.4f}", end="")
            print()
            scaler_q.clear()

        if (i + 1) % args.save_interval == 0:
            ckpt_path = os.path.join(args.checkpoint_dir, f"target_impact_{(i+1)//1000:04d}k.pth")
            torch.save(model.state_dict(), ckpt_path)
            print(f"Saved checkpoint: {ckpt_path}")

    # Save final
    final_path = os.path.join(args.checkpoint_dir, "target_impact_final.pth")
    torch.save(model.state_dict(), final_path)
    print(f"Training complete. Final checkpoint: {final_path}")


if __name__ == "__main__":
    main()
