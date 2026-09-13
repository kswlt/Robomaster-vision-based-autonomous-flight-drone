# run_isaac_gui.ps1 - Launch Isaac Sim GUI for scene debugging only
# GUI is NOT used for formal evaluation (use run_eval.ps1 for headless).

param(
    [string]$IsaacPath = "C:\isaacsim"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $IsaacPath "isaac-sim.bat"))) {
    Write-Error "Isaac Sim not found at $IsaacPath. Install first (see docs/ISAAC_SIM.md)."
    exit 1
}

Write-Output "Launching Isaac Sim GUI (debug only)..."
& (Join-Path $IsaacPath "isaac-sim.bat") --/persistent/isaac/asset_root/default="$RepoRoot\assets"
