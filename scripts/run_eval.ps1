# run_eval.ps1 - Headless automated evaluation (milestone 1 acceptance)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/run_eval.ps1 -Episodes 20
#
# If Isaac Sim is installed, uses Isaac's python.bat for full physics evaluation.
# Otherwise falls back to kinematic-only evaluation with system Python.

param(
    [int]$Episodes = 20,
    [string]$IsaacPath = "C:\isaacsim",
    [switch]$GUI
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$isaacPython = Join-Path $IsaacPath "python.bat"
$useIsaac = Test-Path $isaacPython

if ($useIsaac) {
    $mode = if ($GUI) { "GUI" } else { "headless" }
    Write-Output "=== Running Isaac Sim $mode evaluation: $Episodes episodes ==="
    Write-Output "=== Using Isaac Python: $isaacPython ==="
    $env:ISAAC_PATH = $IsaacPath
    $env:CARB_APP_PATH = Join-Path $IsaacPath "kit"
    $env:EXP_PATH = Join-Path $IsaacPath "apps"

    if ($GUI) {
        & $isaacPython -m sim.isaac.evaluate --episodes $Episodes --gui
    } else {
        & $isaacPython -m sim.isaac.evaluate --episodes $Episodes
    }
} else {
    Write-Output "=== Isaac Sim not found at $IsaacPath ==="
    Write-Output "=== Running kinematic fallback: $Episodes episodes ==="
    Write-Output "=== (This validates logic/metrics, not real physics.) ==="
    python -m sim.isaac.evaluate --episodes $Episodes
}

Write-Output "`n=== Results ==="
if (Test-Path "results\eval_results.json") {
    Get-Content "results\eval_results.json"
}
