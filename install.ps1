#Requires -Version 5.1
$ErrorActionPreference = "Stop"

Write-Host "Installing Swoosh..." -ForegroundColor Cyan

# Check Python
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $python = $cmd
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Write-Host "Error: Python 3.10+ is required" -ForegroundColor Red
    Write-Host "Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found $python" -ForegroundColor Green

# Check pipx
$usePipx = $false
try {
    $null = & pipx --version 2>&1
    $usePipx = $true
} catch {}

if ($usePipx) {
    Write-Host "Installing with pipx..." -ForegroundColor Cyan
    try {
        & pipx install swoosh-cli
    } catch {
        & pipx upgrade swoosh-cli
    }
} else {
    Write-Host "Installing with pip..." -ForegroundColor Cyan
    & $python -m pip install --user swoosh-cli
}

# Verify installation
$swooshPath = $null
try {
    $swooshPath = (Get-Command swoosh -ErrorAction SilentlyContinue).Source
} catch {}

if ($swooshPath) {
    Write-Host ""
    Write-Host "Swoosh installed successfully!" -ForegroundColor Green
    & swoosh --version
} else {
    Write-Host ""
    Write-Host "Swoosh installed." -ForegroundColor Green
    Write-Host "If 'swoosh' is not found, add Python Scripts to PATH:" -ForegroundColor Yellow

    $scriptsPath = & $python -c "import site; print(site.getusersitepackages().replace('site-packages', 'Scripts'))"
    Write-Host "  $scriptsPath" -ForegroundColor Cyan
}

# Check dependencies
Write-Host ""
Write-Host "Checking dependencies..." -ForegroundColor Cyan

# Git
try {
    $gitVersion = & git --version 2>&1
    Write-Host "  git: $gitVersion" -ForegroundColor Green
} catch {
    Write-Host "  git: NOT FOUND (required)" -ForegroundColor Red
    Write-Host "       Install: https://git-scm.com/download/win" -ForegroundColor Yellow
}

# GitHub CLI
try {
    $ghVersion = & gh --version 2>&1 | Select-Object -First 1
    Write-Host "  gh: $ghVersion" -ForegroundColor Green
} catch {
    Write-Host "  gh: NOT FOUND" -ForegroundColor Yellow
    Write-Host "      Install: winget install GitHub.cli" -ForegroundColor Yellow
}

# SSH
try {
    $null = & ssh -V 2>&1
    Write-Host "  ssh: OK" -ForegroundColor Green
} catch {
    Write-Host "  ssh: NOT FOUND (needed for deploy)" -ForegroundColor Yellow
    Write-Host "       Enable OpenSSH in Windows Settings > Apps > Optional Features" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Run 'swoosh doctor' for full system check." -ForegroundColor Cyan
