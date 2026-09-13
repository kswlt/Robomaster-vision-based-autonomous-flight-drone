# run_eval.ps1 - Headless automated evaluation (milestone 1 acceptance)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 20
#
# If Isaac Sim is not installed, falls back to kinematic-only evaluation
# to validate the metrics pipeline (docs/KNOWN_ISSUES.md).

param(
    [int]$Episodes = 20,
    [string]$IsaacPath = "C:\isaacsim",
    [switch]$GUI
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$useIsaac = Test-Path (Join-Path $IsaacPath "isaac-sim.bat")

if ($useIsaac -and -not $GUI) {
    Write-Output "=== Running Isaac Sim headless evaluation: $Episodes episodes ==="
    $env:ISAAC_PATH = $IsaacPath
    python -m sim.isaac.evaluate --episodes $Episodes
} elseif ($useIsaac -and $GUI) {
    Write-Output "=== Running Isaac Sim GUI evaluation: $Episodes episodes ==="
    python -m sim.isaac.evaluate --episodes $Episodes --gui
} else {
    Write-Output "=== Isaac Sim not installed. Running kinematic fallback: $Episodes episodes ==="
    Write-Output "=== (This validates logic/metrics, not real physics. Install Isaac for full eval.) ==="
    python -m sim.isaac.evaluate --episodes $Episodes
}

Write-Output "`n=== Results ==="
if (Test-Path "results\eval_results.json") {
    Get-Content "results\eval_results.json"
}
