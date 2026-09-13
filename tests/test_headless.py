"""Test headless evaluation pipeline (kinematic fallback, no Isaac needed)."""
import json
from pathlib import Path

from sim.common.config import repo_root
from sim.isaac.evaluate import compute_metrics, run_evaluation, save_results
from sim.isaac.episode import EpisodeResult


def test_compute_metrics_empty():
    assert compute_metrics([]) == {}


def test_compute_metrics_all_hits():
    results = [EpisodeResult(episode_id=i, target_hit=True, success=True) for i in range(5)]
    metrics = compute_metrics(results)
    assert metrics["episodes"] == 5
    assert metrics["target_hits"] == 5
    assert metrics["target_hit_rate"] == 1.0
    assert metrics["wrong_collisions"] == 0
    assert metrics["timeouts"] == 0


def test_kinematic_fallback_runs():
    """Full evaluation via kinematic fallback (no Isaac)."""
    metrics = run_evaluation(episodes=5, headless=True)
    assert metrics["episodes"] == 5
    assert "target_hit_rate" in metrics
    assert "wrong_collision_rate" in metrics
    assert "timeout_rate" in metrics


def test_results_saved():
    metrics = run_evaluation(episodes=3, headless=True)
    json_path = repo_root() / "results" / "eval_results.json"
    csv_path = repo_root() / "results" / "eval_results.csv"
    assert json_path.exists()
    assert csv_path.exists()
    data = json.loads(json_path.read_text())
    assert data["episodes"] == 3
