param(
    [switch]$D,
    [switch]$Docker
)

# Encoding settings
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"

# AI Companion Installer (China/Tsinghua Mirror)
# Usage:
#   Online: irm https://raw.githubusercontent.com/Walker7143/ai-companion/master/scripts/install-cn.ps1 -UseBasicParsing -OutFile $env:TEMP\install-cn.ps1; & $env:TEMP\install-cn.ps1
#   Local: .\install-cn.ps1
#   Docker: .\install-cn.ps1 -Docker

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

function Test-Git {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        Write-Host "[OK] Git found: $($git.Source)" -ForegroundColor Green
        return $true
    }
    Write-Host "[FAIL] Git not found" -ForegroundColor Red
    return $false
}

function Install-Git {
    Write-Host ""
    Write-Host "Installing Git..." -ForegroundColor Yellow
    try {
        $null = Start-Process -FilePath "winget" -ArgumentList "install","Git.Git","-s","winget","--accept-source-agreements","--accept-package-agreements" -Wait -PassThru -NoNewWindow
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        Start-Sleep -Seconds 2
        if (Test-Git) {
            Write-Host "[OK] Git installed successfully" -ForegroundColor Green
            return $true
        }
    } catch {
        Write-Host "Automatic Git installation failed" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "Please install Git manually:" -ForegroundColor Yellow
    Write-Host "  1. Download: https://git-scm.com/download/win" -ForegroundColor Gray
    Write-Host "  2. Or run: winget install Git.Git" -ForegroundColor Gray
    Write-Host "  3. Restart PowerShell and run this script again" -ForegroundColor Gray
    return $false
}

function Download-Project {
    param([string]$InstallDir)

    Write-Host ""
    Write-Host "Downloading project to: $InstallDir" -ForegroundColor Cyan

    if (Test-Path $InstallDir) {
        Write-Host "  Cleaning existing directory..." -ForegroundColor Gray
        Remove-Item $InstallDir -Recurse -Force
    }

    # Check if git is available
    if (-not (Test-Git)) {
        if (-not (Install-Git)) {
            return $false
        }
    }

    Write-Host "  Using Git clone..." -ForegroundColor Gray
    $process = Start-Process -FilePath "git" -ArgumentList "clone","--depth","1","https://github.com/Walker7143/ai-companion",$InstallDir -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -eq 0 -and (Test-Path $InstallDir)) {
        Write-Host "  [OK] Download complete" -ForegroundColor Green
        return $true
    }

    Write-Host "  [FAIL] Git clone failed" -ForegroundColor Red
    return $false
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

function Register-GatewayAutostart {
    param([string]$PythonExe)

    Write-Host ""
    Write-Host "Registering Gateway autostart..." -ForegroundColor Yellow
    try {
        & $PythonExe -m ai_companion.autostart
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Gateway autostart registered" -ForegroundColor Green
        } else {
            Write-Host "[WARN] Gateway autostart registration failed" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARN] Gateway autostart registration failed: $_" -ForegroundColor Yellow
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
        # Install runtime dependencies, including local embedding support.
        Write-Host "  Installing runtime dependencies..." -ForegroundColor Gray
        & python -m pip install aiohttp httpx lark-oapi pyyaml pydantic rich jieba python-dotenv aiosqlite chromadb sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple -q

        Write-Host "[OK] Dependencies installed" -ForegroundColor Green

        $needsVenv = Test-NeedsVenv $ProjectDir
        $venvDir = "$userDir\.venv"

        if ($needsVenv) {
            Write-Host ""
            Write-Host "System Python is protected, creating virtual environment..." -ForegroundColor Yellow
            python -m venv $venvDir
            $venvPip = "$venvDir\Scripts\pip.exe"
            & $venvPip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple -q
            & $venvPip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q
            & $venvPip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple -q
            Write-Host "[OK] Installed to virtual environment" -ForegroundColor Green
            Register-GatewayAutostart "$venvDir\Scripts\python.exe"
        } else {
            Write-Host ""
            Write-Host "Installing AI Companion command..." -ForegroundColor Yellow
            & python -m pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple -q
            Write-Host "[OK] AI Companion installed" -ForegroundColor Green
            Register-GatewayAutostart "python"
        }
    } finally {
        Set-Location $originalDir
    }

    # Install frontend UI dependencies (for management dashboard)
    $uiDir = "$ProjectDir\ai-companion-ui"
    if (Test-Path "$uiDir\package.json") {
        Write-Host ""
        Write-Host "Installing frontend UI dependencies..." -ForegroundColor Yellow
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            npm install --prefix "$uiDir"
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[OK] Frontend dependencies installed" -ForegroundColor Green
            } else {
                Write-Host "[WARN] Frontend dependencies failed (dashboard may need manual setup)" -ForegroundColor Yellow
            }
        } else {
            Write-Host "[WARN] npm not found, skipping frontend UI (管理后台需要 npm)" -ForegroundColor Yellow
        }
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
