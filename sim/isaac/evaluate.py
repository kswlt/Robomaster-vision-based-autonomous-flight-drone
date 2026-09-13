"""Headless automated evaluation.

Runs N episodes in Isaac Sim, collects all metrics, outputs JSON + CSV.
Usage: python -m sim.isaac.evaluate --episodes 20
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from sim.common.config import load_config, repo_root
from sim.isaac.episode import EpisodeResult


def compute_metrics(results: list[EpisodeResult]) -> dict[str, Any]:
    """Compute aggregate metrics from per-episode results."""
    n = len(results)
    if n == 0:
        return {}

    hits = [r for r in results if r.target_hit]
    center_hits = [r for r in results if r.center_hit]
    wrong = [r for r in results if r.wrong_collision]
    timeouts = [r for r in results if r.timeout]
    recovered = [r for r in results if r.recovered]
    returned = [r for r in results if r.returned_home]
    complete = [r for r in results if r.target_hit and r.returned_home]

    impact_vels = [r.impact_velocity for r in hits]
    impact_angles = [r.impact_angle_deg for r in hits]
    center_errors = [r.impact_center_error for r in hits]
    times = [r.time_to_target for r in hits]

    return {
        "episodes": n,
        "target_hits": len(hits),
        "target_hit_rate": len(hits) / n,
        "center_hits": len(center_hits),
        "center_hit_rate": len(center_hits) / n,
        "wrong_collisions": len(wrong),
        "wrong_collision_rate": len(wrong) / n,
        "timeouts": len(timeouts),
        "timeout_rate": len(timeouts) / n,
        "impact_velocity_mean": float(np.mean(impact_vels)) if impact_vels else 0.0,
        "impact_velocity_std": float(np.std(impact_vels)) if impact_vels else 0.0,
        "impact_angle_mean": float(np.mean(impact_angles)) if impact_angles else 0.0,
        "impact_angle_p95": float(np.percentile(impact_angles, 95)) if impact_angles else 0.0,
        "impact_center_error_mean": float(np.mean(center_errors)) if center_errors else 0.0,
        "time_to_target_mean": float(np.mean(times)) if times else 0.0,
        "post_impact_recovery_rate": len(recovered) / n,
        "home_return_rate": len(returned) / n,
        "complete_mission_success_rate": len(complete) / n,
    }


def save_results(metrics: dict[str, Any], results: list[EpisodeResult]):
    """Save JSON aggregate + CSV per-episode."""
    out_dir = repo_root() / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "eval_results.json"
    json_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    csv_path = out_dir / "eval_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "episode_id", "success", "target_hit", "center_hit",
            "wrong_collision", "timeout", "impact_velocity",
            "impact_angle_deg", "impact_center_error", "time_to_target",
            "recovered", "returned_home", "steps",
        ])
        for r in results:
            writer.writerow([
                r.episode_id, r.success, r.target_hit, r.center_hit,
                r.wrong_collision, r.timeout, r.impact_velocity,
                r.impact_angle_deg, r.impact_center_error, r.time_to_target,
                r.recovered, r.returned_home, r.steps,
            ])

    return json_path, csv_path


def run_evaluation(episodes: int = 20, headless: bool = True) -> dict[str, Any]:
    """Run full headless evaluation.

    If Isaac Sim is not available, runs a kinematic-only fallback to validate
    the episode logic and metrics pipeline (does NOT use real physics).
    """
    eval_cfg = load_config("evaluation")

    try:
        return _run_isaac(episodes, headless, eval_cfg)
    except ImportError as e:
        print(f"[WARN] Isaac Sim not available ({e}), running kinematic fallback")
        return _run_kinematic_fallback(episodes, eval_cfg)


def _run_isaac(episodes: int, headless: bool, eval_cfg: dict) -> dict:
    from sim.isaac.build_scene import SceneBuilder
    from sim.isaac.episode import EpisodeRunner

    builder = SceneBuilder(headless=headless)
    objects = builder.build_all()
    runner = EpisodeRunner(
        objects["drone"], objects["armor"], objects["camera"],
        objects["arena"], eval_cfg,
    )

    results = []
    for i in range(episodes):
        result = runner.run(episode_id=i)
        results.append(result)
        print(f"Episode {i}: hit={result.target_hit} "
              f"wrong={result.wrong_collision} timeout={result.timeout}")

    builder.close()
    metrics = compute_metrics(results)
    save_results(metrics, results)
    return metrics


def _run_kinematic_fallback(episodes: int, eval_cfg: dict) -> dict:
    """Kinematic-only evaluation (no Isaac) for CI/testing.

    Uses the same Drone/Controller/Episode logic but without physics.
    Validates the metrics pipeline and scripted baseline logic.
    """
    from sim.isaac.drone import Drone
    from sim.isaac.armor_target import ArmorTarget
    from sim.isaac.episode import EpisodeRunner

    drone_cfg = load_config("drone")
    armor_cfg = load_config("armor")

    drone = Drone(drone_cfg)
    armor = ArmorTarget(armor_cfg)
    runner = EpisodeRunner(drone, armor, None, None, eval_cfg)

    results = []
    for i in range(episodes):
        result = runner.run(episode_id=i)
        results.append(result)

    metrics = compute_metrics(results)
    save_results(metrics, results)
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Headless evaluation")
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--gui", action="store_true", help="Show Isaac GUI (debug only)")
    args = parser.parse_args()

    metrics = run_evaluation(episodes=args.episodes, headless=not args.gui)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
