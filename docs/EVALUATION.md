# Evaluation

Isaac Sim headless, independent validator.

## Command
```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 20
```

## Output
- `results/eval_results.json` — aggregate metrics
- `results/eval_results.csv` — per-episode details

## Metrics (all required)
episodes, target_hits, target_hit_rate, center_hits, center_hit_rate,
wrong_collisions, wrong_collision_rate, timeouts, timeout_rate,
impact_velocity_mean, impact_velocity_std, impact_angle_mean, impact_angle_p95,
impact_center_error_mean, time_to_target_mean, post_impact_recovery_rate,
home_return_rate, complete_mission_success_rate

## Mission States
TAKEOFF → ATTACK → HIT → RECOVER → RETURN → HOME

## Thresholds (milestone 1)
- target_hit_rate ≥ 0.95
- wrong_collision_rate ≤ 0.05
- timeout_rate ≤ 0.05

## Current Status
Code written, not executed (Isaac not installed).
