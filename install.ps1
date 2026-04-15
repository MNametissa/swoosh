#Requires -Version 5.1
<#
.SYNOPSIS
    Swoosh installer for Windows
.DESCRIPTION
    Installs Swoosh and all dependencies (Python, Git, GitHub CLI, OpenSSH)
    Uses winget (preferred), scoop, or chocolatey
.EXAMPLE
    iwr -useb https://raw.githubusercontent.com/MNametissa/swoosh/main/install.ps1 | iex
#>

$ErrorActionPreference = "Stop"

# Colors
function Write-Info { param($msg) Write-Host $msg -ForegroundColor Cyan }
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host $msg -ForegroundColor Red }

# Check if running as admin
function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Detect package manager
function Get-PackageManager {
    if (Get-Command winget -ErrorAction SilentlyContinue) { return "winget" }
    if (Get-Command scoop -ErrorAction SilentlyContinue) { return "scoop" }
    if (Get-Command choco -ErrorAction SilentlyContinue) { return "choco" }
    return $null
}

# Install winget if not present (Windows 10/11)
function Install-Winget {
    if (Get-Command winget -ErrorAction SilentlyContinue) { return $true }

    Write-Info "Installing winget..."

    # Check Windows version
    $build = [System.Environment]::OSVersion.Version.Build
    if ($build -lt 17763) {
        Write-Warn "Windows 10 1809+ required for winget"
        return $false
    }

    try {
        # Install via Microsoft Store App Installer
        $progressPreference = 'silentlyContinue'
        $url = "https://aka.ms/getwinget"
        $outFile = "$env:TEMP\Microsoft.DesktopAppInstaller.msixbundle"
        Invoke-WebRequest -Uri $url -OutFile $outFile -UseBasicParsing
        Add-AppxPackage -Path $outFile
        Remove-Item $outFile -Force
        return $true
    } catch {
        Write-Warn "Could not install winget automatically"
        Write-Warn "Install from Microsoft Store: 'App Installer'"
        return $false
    }
}

# Install package
function Install-Package {
    param(
        [string]$Name,
        [string]$WingetId,
        [string]$ScoopName,
        [string]$ChocoName
    )

    $pm = Get-PackageManager

    Write-Info "Installing $Name..."

    switch ($pm) {
        "winget" {
            winget install --id $WingetId --accept-source-agreements --accept-package-agreements -e -h
        }
        "scoop" {
            scoop install $ScoopName
        }
        "choco" {
            choco install $ChocoName -y
        }
        default {
            Write-Warn "No package manager found. Please install $Name manually."
            return $false
        }
    }

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    return $true
}

# Enable OpenSSH
function Install-OpenSSH {
    if (Get-Command ssh -ErrorAction SilentlyContinue) {
        Write-Success "  ssh: OK"
        return
    }

    Write-Info "Installing OpenSSH..."

    # Try Windows capability first (Windows 10 1809+)
    try {
        $capability = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Client*'
        if ($capability.State -ne 'Installed') {
            Add-WindowsCapability -Online -Name 'OpenSSH.Client~~~~0.0.1.0'
        }
        Write-Success "  ssh: installed"
        return
    } catch {}

    # Fallback to package manager
    $pm = Get-PackageManager
    if ($pm -eq "winget") {
        winget install Microsoft.OpenSSH.Beta -e -h
    } elseif ($pm -eq "scoop") {
        scoop install openssh
    } elseif ($pm -eq "choco") {
        choco install openssh -y
    } else {
        Write-Warn "  ssh: Please enable OpenSSH in Windows Settings > Apps > Optional Features"
    }
}

# Main installation
Write-Host ""
Write-Host "======================================" -ForegroundColor White
Write-Host "       Swoosh Installer (Windows)" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor White
Write-Host ""

# Detect/install package manager
$pm = Get-PackageManager
if (-not $pm) {
    Write-Info "No package manager found. Installing winget..."
    if (Install-Winget) {
        $pm = "winget"
    } else {
        Write-Warn "Please install one of: winget, scoop, or chocolatey"
        Write-Host "  winget: https://aka.ms/getwinget"
        Write-Host "  scoop:  irm get.scoop.sh | iex"
        Write-Host "  choco:  https://chocolatey.org/install"
        exit 1
    }
}

Write-Info "Using package manager: $pm"
Write-Host ""

# 1. Python 3.10+
Write-Info "Checking Python..."
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $version = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($version) {
            $parts = $version.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $python = $cmd
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Install-Package -Name "Python" -WingetId "Python.Python.3.12" -ScoopName "python" -ChocoName "python312"
    $python = "python"

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

try {
    $pyVersion = & $python --version 2>&1
    Write-Success "  python: $pyVersion"
} catch {
    Write-Err "  python: installation failed"
    exit 1
}

# 2. Git
Write-Info "Checking Git..."
if (Get-Command git -ErrorAction SilentlyContinue) {
    $gitVersion = git --version
    Write-Success "  git: $gitVersion"
} else {
    Install-Package -Name "Git" -WingetId "Git.Git" -ScoopName "git" -ChocoName "git"
    Write-Success "  git: installed"
}

# 3. GitHub CLI
Write-Info "Checking GitHub CLI..."
if (Get-Command gh -ErrorAction SilentlyContinue) {
    $ghVersion = (gh --version | Select-Object -First 1)
    Write-Success "  gh: $ghVersion"
} else {
    Install-Package -Name "GitHub CLI" -WingetId "GitHub.cli" -ScoopName "gh" -ChocoName "gh"
    Write-Success "  gh: installed"
}

# 4. OpenSSH
Write-Info "Checking SSH..."
Install-OpenSSH

Write-Host ""

# 5. Install pipx
Write-Info "Setting up pipx..."
if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    & $python -m pip install --user pipx 2>$null
    & $python -m pipx ensurepath 2>$null

    # Add to current session PATH
    $userBase = & $python -c "import site; print(site.getuserbase())"
    $scriptsPath = Join-Path $userBase "Scripts"
    if (Test-Path $scriptsPath) {
        $env:Path = "$scriptsPath;$env:Path"
    }
}
Write-Success "  pipx: OK"

# 6. Install Swoosh
Write-Host ""
Write-Info "Installing Swoosh..."

# Install from PyPI
& pipx install swoosh-cli
Write-Success "  swoosh: installed from PyPI"

# Ensure pipx bin is in PATH for this session
$pipxBin = "$env:USERPROFILE\.local\bin"
if (Test-Path $pipxBin) {
    $env:Path = "$pipxBin;$env:Path"
}

Write-Host ""
Write-Host "======================================" -ForegroundColor White
Write-Success "  Swoosh installed successfully!"
Write-Host "======================================" -ForegroundColor White
Write-Host ""

# Verify
if (Get-Command swoosh -ErrorAction SilentlyContinue) {
    & swoosh --version
} else {
    Write-Warn "Restart your terminal to use swoosh"
    Write-Host ""
    Write-Host "Or add to PATH manually:"
    Write-Host "  `$env:Path = `"$pipxBin;`$env:Path`""
}

Write-Host ""
Write-Info "Next steps:"
Write-Host "  1. Run: swoosh auth"
Write-Host "  2. Run: swoosh doctor"
Write-Host "  3. Run: swoosh init myproject"
Write-Host ""

# Offer to run auth now
$response = Read-Host "Run 'swoosh auth' now? [Y/n]"
if ($response -ne 'n' -and $response -ne 'N') {
    & swoosh auth
}
