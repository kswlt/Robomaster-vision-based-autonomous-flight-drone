# check_environment.ps1 - Reproducible environment audit
# Writes docs/ENVIRONMENT.md and prints summary to console.

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$OutFile = Join-Path $RepoRoot "docs\ENVIRONMENT.md"

function Get-Section($title) { "`n## $title`n" }

$lines = @()
$lines += "# Environment Audit`n"
$lines += "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm')`n"
$lines += "Script: scripts/check_environment.ps1 (reproducible)`n"

# OS
$os = Get-CimInstance Win32_OperatingSystem
$lines += Get-Section "Host System"
$lines += "| Item | Value |"
$lines += "|------|-------|"
$lines += "| OS | $($os.Caption) $($os.Version) |"
$lines += "| RAM | $([math]::Round($os.TotalVisibleMemorySize/1MB,1)) GB |"
Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    $lines += "| Disk $($_.Name): | $([math]::Round($_.Free/1GB,1)) GB free / $([math]::Round(($_.Used+$_.Free)/1GB,1)) GB total |"
}

# GPU
$lines += Get-Section "GPU"
$nvidia = nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1
$lines += "| Item | Value |"
$lines += "|------|-------|"
$lines += "| GPU | $nvidia |"
try { $nvcc = (nvcc --version 2>&1 | Select-Object -Last 1); $lines += "| CUDA toolkit (nvcc) | $nvcc |" } catch { $lines += "| CUDA toolkit | not found |" }

# Tools
$lines += Get-Section "Development Tools"
$lines += "| Item | Value |"
$lines += "|------|-------|"
$lines += "| Python (default) | $(python --version 2>&1) |"
$lines += "| Git | $(git --version) |"
try { $lines += "| CMake | $((cmake --version 2>&1 | Select-Object -First 1)) |" } catch { $lines += "| CMake | not found |" }
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $vs = & $vswhere -products * -format json 2>&1 | ConvertFrom-Json
    if ($vs) { $vs | ForEach-Object { $lines += "| Visual Studio | $($_.displayName) $($_.installationVersion) |" } }
    else { $lines += "| Visual Studio | not detected |" }
} else { $lines += "| Visual Studio | vswhere not found |" }

# WSL
$lines += Get-Section "WSL2"
$wslStatus = wsl --status 2>&1
$lines += "```$wslStatus```"
$wslList = wsl -l -v 2>&1
$lines += "```$wslList```"

# Docker
try { $lines += "`n## Docker`n```$(docker --version 2>&1)```" } catch { $lines += "`n## Docker`nNot found" }

# Isaac Sim
$lines += Get-Section "Isaac Sim"
$isaacPaths = @("C:\isaacsim", "C:\Program Files\NVIDIA Corporation\Isaac Sim", "$env:LOCALAPPDATA\ov\pkg")
$found = $false
foreach ($p in $isaacPaths) { if (Test-Path $p) { $lines += "| Installed at | $p |"; $found = $true } }
if (-not $found) {
    $lines += "| Installed | **No** |"
    $lines += "| Target version | 6.1.0 (standalone ZIP, 9.66 GB) |"
    $lines += "| Download | https://downloads.isaacsim.nvidia.com/isaac-sim-standalone-6.1.0-windows-x86_64.zip |"
    $lines += "| **Blocker** | **Insufficient disk space** — need ~40 GB free |"
}

# Network
$lines += Get-Section "Network / Proxy"
$lines += "| Item | Value |"
$lines += "|------|-------|"
$lines += "| HTTP_PROXY | $env:HTTP_PROXY |"
$lines += "| HTTPS_PROXY | $env:HTTPS_PROXY |"
$clash = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 7890 }
if ($clash) { $lines += "| Clash | listening on 127.0.0.1:7890 |" } else { $lines += "| Clash | not detected on 7890 |" }

# Git
$lines += Get-Section "Git"
$lines += "| Item | Value |"
$lines += "|------|-------|"
$lines += "| Remote | $(git -C $RepoRoot remote get-url origin 2>&1) |"
$lines += "| Branch | $(git -C $RepoRoot branch --show-current 2>&1) |"
$lines += "| User | $(git -C $RepoRoot config user.name) <$(git -C $RepoRoot config user.email)> |"

$lines -join "`n" | Set-Content -Path $OutFile -Encoding UTF8
Write-Output "Environment audit written to $OutFile"
Write-Output "--- Summary ---"
Write-Output "OS: $($os.Caption)"
Write-Output "GPU: $nvidia"
Write-Output "Python: $(python --version 2>&1)"
Write-Output "WSL: $(wsl -l -v 2>&1 | Select-Object -First 3)"
Write-Output "Isaac Sim: $(if ($found) {'Installed'} else {'NOT installed (disk blocker)'})"
