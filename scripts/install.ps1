[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# AI Companion 一键安装脚本
# 支持: Windows PowerShell
#
# 用法:
#   . {iwr https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master/scripts/install.ps1 -UseBasicParsing} | iex  # 在线安装（推荐）
#   .\install.ps1          # 本地安装
#   .\install.ps1 -Docker  # Docker 安装

param(
    [switch]$D,
    [switch]$Docker
)

$ErrorActionPreference = "Stop"

$InstallMode = "local"
if ($D -or $Docker) {
    $InstallMode = "docker"
}

# 检测是否从远程执行
$ScriptPath = $MyInvocation.MyCommand.Path
$IsOnlineInstall = $false
if ([string]::IsNullOrEmpty($ScriptPath) -or $ScriptPath -eq "" -or $ScriptPath -match "Temp|Local\\Temp" -or ($env:ONLINE_INSTALL -eq "1")) {
    $IsOnlineInstall = $true
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Companion Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检测 Docker
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

# 检测 Python
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
        Write-Host "[FAIL] Python version too old or not found" -ForegroundColor Red
        return $false
    } catch {
        Write-Host "[FAIL] Python 3.11+ required" -ForegroundColor Red
        return $false
    }
}

# 检测 pip
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

# 下载项目
function Download-Project {
    param([string]$InstallDir)

    Write-Host ""
    Write-Host "Downloading project to: $InstallDir" -ForegroundColor Cyan

    $repoUrl = "https://gitee.com/wang_xiao_wei_7143/ai-girl-friend"

    # 先清理已存在的目录
    if (Test-Path $InstallDir) {
        Write-Host "  Cleaning existing directory..." -ForegroundColor Gray
        Remove-Item $InstallDir -Recurse -Force
    }

    # 方法1: 使用 git clone
    $hasGit = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
    if ($hasGit) {
        Write-Host "  Using Git clone..." -ForegroundColor Gray
        $process = Start-Process -FilePath "git" -ArgumentList "clone","--depth","1",$repoUrl,$InstallDir -NoNewWindow -Wait -PassThru
        if ($process.ExitCode -eq 0 -and (Test-Path $InstallDir)) {
            Write-Host "  [OK] Download complete" -ForegroundColor Green
            return $true
        }
        Write-Host "  [WARN] Git clone failed" -ForegroundColor Yellow
    } else {
        Write-Host "  [WARN] Git not found" -ForegroundColor Yellow
    }

    # 方法2: 直接下载文件（无需 Git）
    Write-Host "  Trying direct download..." -ForegroundColor Gray
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        New-Item -Path $InstallDir -ItemType Directory -Force | Out-Null

        $baseUrl = "https://gitee.com/wang_xiao_wei_7143/ai-girl-friend/raw/master"

        # 需要下载的文件和目录结构
        $files = @(
            "requirements.txt",
            "setup.py",
            "pyproject.toml",
            "ai_companion/__main__.py",
            "ai_companion/__init__.py",
            "ai_companion/config.py",
            "ai_companion/bot.py",
            "ai_companion/models.py"
        )

        foreach ($file in $files) {
            $fileUrl = "$baseUrl/$file"
            $localPath = Join-Path $InstallDir $file
            $dir = Split-Path $localPath
            if (!(Test-Path $dir)) { New-Item -Path $dir -ItemType Directory -Force | Out-Null }
            Write-Host "    Downloading $file..." -ForegroundColor Gray
            Invoke-WebRequest -Uri $fileUrl -OutFile $localPath -UseBasicParsing
        }

        Write-Host "  [OK] Download complete" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  [FAIL] Direct download failed: $_" -ForegroundColor Red
        return $false
    }
}

# 检查是否需要虚拟环境
function Test-NeedsVenv {
    param([string]$ProjectDir)
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        $output = python -m pip list 2>&1 | Out-String
        if ($output -match "externally-managed-environment") {
            return $true
        }
        $testFile = "$env:TEMP\pip_test.txt"
        $null = python -m pip install --target $testFile --dry-run pip 2>&1
        if ($LASTEXITCODE -ne 0) { return $true }
        if (Test-Path $testFile) { Remove-Item $testFile -Force -ErrorAction SilentlyContinue }
        return $false
    } catch {
        return $true
    } finally {
        Set-Location $originalDir
    }
}

# 本地安装
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
    if (-not (Test-Path "$userDir\config\bots.yaml")) {
        New-Item -ItemType Directory -Path "$userDir\config" -Force | Out-Null
        Copy-Item "$ProjectDir\config\bots.yaml.example" "$userDir\config\bots.yaml" -ErrorAction SilentlyContinue
        Copy-Item "$ProjectDir\config\models.yaml.example" "$userDir\config\models.yaml" -ErrorAction SilentlyContinue
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

# Docker 安装
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

# 主流程
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
