# export_rk3588.ps1 - Export trained policy to ONNX and RKNN for RK3588
# Usage: powershell -ExecutionPolicy Bypass -File scripts/export_rk3588.ps1

param(
    [string]$Checkpoint = "results\checkpoints\best.pt",
    [string]$OnnxOut = "deployment\onnx\policy.onnx",
    [string]$RknnOut = "deployment\rk3588\policy.rknn"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not (Test-Path $Checkpoint)) {
    Write-Error "Checkpoint not found: $Checkpoint. Train a policy first."
    exit 1
}

Write-Output "=== Exporting PyTorch checkpoint to ONNX ==="
python deployment\common\export_onnx.py --checkpoint $Checkpoint --output $OnnxOut

Write-Output "=== ONNX export complete: $OnnxOut ==="
Write-Output "=== RKNN export requires RKNN Toolkit2 (run on Linux/RK3588 build host) ==="
Write-Output "  python deployment/rk3588/export_rknn.py --onnx $OnnxOut --output $RknnOut"
Write-Output "=== Benchmark on RK3588 ==="
Write-Output "  python deployment/rk3588/benchmark.py --model $RknnOut"
