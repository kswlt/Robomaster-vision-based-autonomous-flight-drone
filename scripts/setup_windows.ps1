# setup_windows.ps1 - Windows-side setup for asset analysis and testing
# Does NOT install Isaac Sim (disk blocker). Installs Python deps for analysis.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Output "=== Installing Python analysis dependencies ==="
python -m pip install --upgrade pip --quiet
python -m pip install numpy trimesh networkx matplotlib pyyaml --quiet

Write-Output "=== Verifying imports ==="
python -c "import numpy, trimesh, networkx, matplotlib, yaml; print('All imports OK')"

Write-Output "=== Running asset analysis ==="
python scripts/analyze_arena_stl.py
python scripts/analyze_arena_components.py
python scripts/scan_armor_plates.py
python scripts/preview_arena.py

Write-Output "=== Setup complete ==="
Write-Output "NOTE: Isaac Sim is NOT installed (disk space blocker)."
Write-Output "To install Isaac Sim later, free >=40GB on C: then run:"
Write-Output "  mkdir C:\isaacsim"
Write-Output "  tar -xvzf isaac-sim-standalone-6.1.0-windows-x86_64.zip -C C:\isaacsim"
Write-Output "  cd C:\isaacsim; .\post_install.bat"
