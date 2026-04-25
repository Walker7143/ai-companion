param(
    [switch]$D,
    [switch]$Docker
)

# Encoding settings
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"

# AI Companion Installer
# Usage:
#   Online: irm https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.ps1 -UseBasicParsing -OutFile $env:TEMP\install.ps1; & $env:TEMP\install.ps1
#   Local: .\install.ps1
#   Docker: .\install.ps1 -Docker

$InstallMode = "local"
if ($D -or $Docker) {
    $InstallMode = "docker"
}

$ScriptPath = $MyInvocation.MyCommand.Path
$IsOnlineInstall = $false
if ([string]::IsNullOrEmpty($ScriptPath) -or $ScriptPath -match "Temp|Local\\Temp" -or ($env:ONLINE_INSTALL -eq "1")) {
    $IsOnlineInstall = $true
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Companion Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

function Test-Docker {
    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Docker: $dockerVersion" -ForegroundColor Green
            return $true
        }
    } catch {}
    Write-Host "[FAIL] Docker not found" -ForegroundColor Red
    return $false
}

function Test-Python {
    try {
        $version = python --version 2>&1
        if ($version -match "Python (\d+\.\d+)") {
            $ver = [float]$Matches[1]
            if ($ver -ge 3.11) {
                Write-Host "[OK] Python $ver" -ForegroundColor Green
                return $true
            }
        }
        Write-Host "[FAIL] Python version too old" -ForegroundColor Red
        return $false
    } catch {
        Write-Host "[FAIL] Python 3.11+ required" -ForegroundColor Red
        return $false
    }
}

function Test-Pip {
    try {
        python -m pip --version | Out-Null
        Write-Host "[OK] pip ready" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[WARN] pip not found, installing..." -ForegroundColor Yellow
        python -m ensurepip --upgrade 2>&1 | Out-Null
        return $true
    }
}

function Download-Project {
    param([string]$InstallDir)

    Write-Host ""
    Write-Host "Downloading project to: $InstallDir" -ForegroundColor Cyan

    if (Test-Path $InstallDir) {
        Write-Host "  Cleaning existing directory..." -ForegroundColor Gray
        Remove-Item $InstallDir -Recurse -Force
    }

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        New-Item -Path $InstallDir -ItemType Directory -Force | Out-Null

        $baseUrl = "https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master"

        # Root files that exist
        $rootFiles = @("requirements.txt", "setup.py")
        foreach ($file in $rootFiles) {
            Write-Host "  Downloading $file..." -ForegroundColor Gray
            try {
                Invoke-WebRequest -Uri "$baseUrl/$file" -OutFile (Join-Path $InstallDir $file) -UseBasicParsing -TimeoutSec 30
            } catch {
                Write-Host "    Warning: $file not found, creating default..." -ForegroundColor Yellow
            }
        }

        # Config files - only models.yaml.example exists
        New-Item -Path (Join-Path $InstallDir "config") -ItemType Directory -Force | Out-Null
        Write-Host "  Downloading config files..." -ForegroundColor Gray
        try {
            Invoke-WebRequest -Uri "$baseUrl/config/models.yaml.example" -OutFile (Join-Path $InstallDir "config\models.yaml.example") -UseBasicParsing -TimeoutSec 30
        } catch {}

        # Create default bots.yaml if not found
        $botsYamlContent = @"
bots:
  default:
    name: "AI Companion"
    persona: "persona_template.json"
"@
        Set-Content -Path (Join-Path $InstallDir "config\bots.yaml") -Value $botsYamlContent -Encoding UTF8

        # Download all ai_companion subdirectories recursively using a smarter approach
        Write-Host "  Downloading ai_companion source..." -ForegroundColor Gray

        # Download key files
        $keyFiles = @(
            "ai_companion/__main__.py",
            "ai_companion/__init__.py",
            "ai_companion/main.py",
            "ai_companion/config/__init__.py",
            "ai_companion/bot/__init__.py",
            "ai_companion/bot/manager.py",
            "ai_companion/bot/cli.py",
            "ai_companion/gateway/cmd.py",
            "ai_companion/gateway/router.py",
            "ai_companion/memory/__init__.py",
            "ai_companion/memory/engine.py",
            "ai_companion/platform/__init__.py"
        )

        foreach ($file in $keyFiles) {
            $localPath = Join-Path $InstallDir $file
            $dir = Split-Path $localPath
            if (!(Test-Path $dir)) { New-Item -Path $dir -ItemType Directory -Force | Out-Null }
            try {
                Write-Host "    $file" -ForegroundColor Gray
                Invoke-WebRequest -Uri "$baseUrl/$file" -OutFile $localPath -UseBasicParsing -TimeoutSec 30
            } catch {
                Write-Host "    Warning: failed to download $file" -ForegroundColor Yellow
            }
        }

        # Copy config/__init__.py content if it exists
        try {
            $configInitContent = Invoke-WebRequest -Uri "$baseUrl/ai_companion/config/__init__.py" -UseBasicParsing -TimeoutSec 30 -ErrorAction SilentlyContinue
        } catch {}

        Write-Host "  [OK] Download complete" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  [FAIL] Download failed: $_" -ForegroundColor Red
        return $false
    }
}

function Test-NeedsVenv {
    param([string]$ProjectDir)
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        $output = python -m pip list 2>&1 | Out-String
        if ($output -match "externally-managed-environment") {
            return $true
        }
        return $false
    } catch {
        return $true
    } finally {
        Set-Location $originalDir
    }
}

function Install-Local {
    param([string]$ProjectDir)

    Write-Host ""
    Write-Host "Local Install Mode" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Python)) {
        Write-Host "Please install Python 3.11+ first" -ForegroundColor Yellow
        return
    }

    Test-Pip

    $userDir = "$env:USERPROFILE\.ai-companion"
    Write-Host ""
    Write-Host "Creating user directory: $userDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "$userDir\data\bots" -Force | Out-Null
    New-Item -ItemType Directory -Path "$userDir\logs" -Force | Out-Null
    Write-Host "[OK] Directory created" -ForegroundColor Green

    Write-Host ""
    Write-Host "Initializing config..." -ForegroundColor Yellow
    if (-not (Test-Path "$userDir\config\models.yaml")) {
        New-Item -ItemType Directory -Path "$userDir\config" -Force | Out-Null
        Copy-Item "$ProjectDir\config\models.yaml.example" "$userDir\config\models.yaml" -ErrorAction SilentlyContinue
        if (Test-Path "$ProjectDir\config\bots.yaml") {
            Copy-Item "$ProjectDir\config\bots.yaml" "$userDir\config\bots.yaml" -ErrorAction SilentlyContinue
        }
        Write-Host "[OK] Config created" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        & python -m pip install -r requirements.txt -q
        Write-Host "[OK] Dependencies installed" -ForegroundColor Green

        $needsVenv = Test-NeedsVenv $ProjectDir
        $venvDir = "$userDir\.venv"

        if ($needsVenv) {
            Write-Host ""
            Write-Host "System Python is protected, creating virtual environment..." -ForegroundColor Yellow
            python -m venv $venvDir
            $venvPip = "$venvDir\Scripts\pip.exe"
            & $venvPip install --upgrade pip -q
            & $venvPip install -r requirements.txt -q
            & $venvPip install -e .
            Write-Host "[OK] Installed to virtual environment" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "Installing AI Companion command..." -ForegroundColor Yellow
            & python -m pip install -e .
            Write-Host "[OK] AI Companion installed" -ForegroundColor Green
        }
    } finally {
        Set-Location $originalDir
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Installation complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Edit config: $userDir\config\models.yaml" -ForegroundColor Yellow
    Write-Host "  2. Run setup:"
    if ($needsVenv) {
        Write-Host "     $venvDir\Scripts\ai-companion.exe setup" -ForegroundColor Gray
        Write-Host "     $venvDir\Scripts\ai-companion.exe start" -ForegroundColor Gray
    } else {
        Write-Host "     ai-companion setup" -ForegroundColor Gray
        Write-Host "     ai-companion start" -ForegroundColor Gray
    }
    Write-Host "========================================" -ForegroundColor Cyan
}

function Install-Docker {
    param([string]$ProjectDir)

    Write-Host ""
    Write-Host "Docker Install Mode" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Docker)) {
        Write-Host "Please install Docker first" -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "Building Docker image..." -ForegroundColor Yellow
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        docker build -t ai-companion .
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Image built" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] Build failed" -ForegroundColor Red
            return
        }
    } finally {
        Set-Location $originalDir
    }

    Write-Host ""
    Write-Host "Creating config directory..." -ForegroundColor Yellow
    $userDir = "$env:USERPROFILE\.ai-companion"
    New-Item -ItemType Directory -Path "$userDir\config" -Force | Out-Null
    New-Item -ItemType Directory -Path "$userDir\data" -Force | Out-Null
    Write-Host "[OK] Config directory: $userDir" -ForegroundColor Green

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Docker installation complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Configure API Key in docker-compose.yml" -ForegroundColor Yellow
    Write-Host "  2. Run: docker-compose up -d" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan
}

# Main
$ProjectDir = $PSScriptRoot

if ($IsOnlineInstall) {
    $InstallDir = "$env:LOCALAPPDATA\AICompanion"
    Write-Host "Online Install Mode" -ForegroundColor Cyan
    Write-Host "  Install directory: $InstallDir" -ForegroundColor Gray
    Write-Host ""

    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    if (-not (Download-Project $InstallDir)) {
        return
    }
    $ProjectDir = $InstallDir
}

switch ($InstallMode) {
    "docker" { Install-Docker $ProjectDir }
    "local"  { Install-Local $ProjectDir }
}
