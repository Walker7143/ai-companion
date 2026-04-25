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

Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  AI Companion 安装脚本" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# 检测 Docker
function Test-Docker {
    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Docker 已就绪: $dockerVersion" -ForegroundColor Green
            return $true
        }
    } catch {}
    Write-Host "❌ 未检测到 Docker" -ForegroundColor Red
    return $false
}

# 检测 Python
function Test-Python {
    try {
        $version = python --version 2>&1
        if ($version -match "Python (\d+\.\d+)") {
            $ver = [float]$Matches[1]
            if ($ver -ge 3.11) {
                Write-Host "✓ Python $ver" -ForegroundColor Green
                return $true
            }
        }
        Write-Host "❌ Python 版本过低或未安装" -ForegroundColor Red
        Write-Host "请先安装 Python 3.11+: https://www.python.org/downloads/" -ForegroundColor Yellow
        return $false
    } catch {
        try {
            $version = python3 --version 2>&1
            if ($version -match "Python (\d+\.\d+)") {
                $ver = [float]$Matches[1]
                if ($ver -ge 3.11) {
                    Write-Host "✓ Python $ver" -ForegroundColor Green
                    return $true
                }
            }
        } catch {}
        Write-Host "❌ 未检测到 Python 3.11+" -ForegroundColor Red
        Write-Host "请先安装 Python: https://www.python.org/downloads/" -ForegroundColor Yellow
        return $false
    }
}

# 检测 pip
function Test-Pip {
    try {
        python -m pip --version | Out-Null
        Write-Host "✓ pip 已就绪" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "📦 安装 pip..." -ForegroundColor Yellow
        python -m ensurepip --upgrade 2>&1 | Out-Null
        return $true
    }
}

# 下载项目
function Download-Project {
    param([string]$InstallDir)

    Write-Host ""
    Write-Host "Downloading AI Companion code..." -ForegroundColor Yellow

    $repoUrl = "https://gitee.com/wang_xiao_wei_7143/ai-girl-friend"

    # 先清理已存在的目录
    if (Test-Path $InstallDir) {
        Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    try {
        # 使用 git clone
        Write-Host "   Using Git clone..." -ForegroundColor Gray
        $output = git clone --depth 1 $repoUrl $InstallDir 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Done!" -ForegroundColor Green
            return $true
        }
        Write-Host "   Git clone failed with exit code: $LASTEXITCODE" -ForegroundColor Gray
        Write-Host "   Output: $output" -ForegroundColor Gray
    } catch {
        Write-Host "   Git clone exception: $_" -ForegroundColor Gray
    }

    Write-Host "Failed to download. Please ensure Git is installed and network is working." -ForegroundColor Red
    return $false
}

# 检查是否需要创建虚拟环境
function Test-NeedsVenv {
    param([string]$ProjectDir)
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        $null = python -m pip list 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $true
        }
        $output = python -m pip list 2>&1 | Out-String
        if ($output -match "externally-managed-environment") {
            return $true
        }
        # 尝试实际安装测试
        $testFile = "$env:TEMP\pip_test_$([guid]::NewGuid().ToString('N')).txt"
        $null = python -m pip install --target $testFile --dry-run pip 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $true
        }
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
    Write-Host "📦 本地安装模式" -ForegroundColor Cyan
    Write-Host ""

    # Python 检查
    if (-not (Test-Python)) {
        Write-Host ""
        Write-Host "❌ 本地安装需要 Python 3.11+" -ForegroundColor Red
        Write-Host "请安装 Python 或使用 Docker 模式" -ForegroundColor Yellow
        return
    }

    # pip 检查
    Test-Pip

    # 用户数据目录
    $userDir = "$env:USERPROFILE\.ai-companion"
    Write-Host ""
    Write-Host "📁 创建用户数据目录: $userDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "$userDir\data\bots" -Force | Out-Null
    New-Item -ItemType Directory -Path "$userDir\logs" -Force | Out-Null
    Write-Host "✓ 数据目录创建完成" -ForegroundColor Green

    # 复制配置文件
    Write-Host ""
    Write-Host "⚙️  初始化配置..." -ForegroundColor Yellow
    if (-not (Test-Path "$userDir\config\bots.yaml")) {
        New-Item -ItemType Directory -Path "$userDir\config" -Force | Out-Null
        Copy-Item "$ProjectDir\config\bots.yaml.example" "$userDir\config\bots.yaml" -ErrorAction SilentlyContinue
        Copy-Item "$ProjectDir\config\models.yaml.example" "$userDir\config\models.yaml" -ErrorAction SilentlyContinue
        Write-Host "✓ 配置文件已创建" -ForegroundColor Green
    }

    # 安装依赖
    Write-Host ""
    Write-Host "📦 安装 Python 依赖..." -ForegroundColor Yellow
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        & python -m pip install -r requirements.txt -q
        Write-Host "✓ 依赖安装完成" -ForegroundColor Green

        # 检查是否需要虚拟环境
        $needsVenv = Test-NeedsVenv $ProjectDir
        $venvDir = "$userDir\.venv"

        if ($needsVenv) {
            Write-Host ""
            Write-Host "   系统 Python 受保护，创建虚拟环境..." -ForegroundColor Yellow
            python -m venv $venvDir
            $venvPip = "$venvDir\Scripts\pip.exe"
            & $venvPip install --upgrade pip -q
            & $venvPip install -r requirements.txt -q
            & $venvPip install -e .
            Write-Host "✓ AI Companion 已安装到虚拟环境" -ForegroundColor Green
            Write-Host ""
            Write-Host "   启动命令: $venvDir\Scripts\ai-companion.exe" -ForegroundColor Gray
        } else {
            # 安装 AI Companion（全局命令）
            Write-Host ""
            Write-Host "📦 安装 AI Companion（全局命令）..." -ForegroundColor Yellow
            & python -m pip install -e .
            Write-Host "✓ AI Companion 命令已安装: ai-companion" -ForegroundColor Green
        }
    } finally {
        Set-Location $originalDir
    }

    Write-Host ""
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "✓ 本地安装完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "下一步:" -ForegroundColor White
    Write-Host "  1. 配置 API Key:" -ForegroundColor Yellow
    Write-Host "     编辑 $userDir\config\models.yaml" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. 启动:" -ForegroundColor Yellow
    if ($needsVenv) {
        Write-Host "     $venvDir\Scripts\ai-companion.exe setup" -ForegroundColor Gray
        Write-Host "     $venvDir\Scripts\ai-companion.exe start" -ForegroundColor Gray
    } else {
        Write-Host "     ai-companion setup" -ForegroundColor Gray
        Write-Host "     ai-companion start" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host "  配置目录: $userDir" -ForegroundColor Gray
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
}

# Docker 安装
function Install-Docker {
    param([string]$ProjectDir)

    Write-Host ""
    Write-Host "🐳 Docker 安装模式" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Docker)) {
        Write-Host ""
        Write-Host "请先安装 Docker: https://docs.docker.com/get-docker/" -ForegroundColor Yellow
        Write-Host "或使用本地安装模式" -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "📦 构建 Docker 镜像..." -ForegroundColor Yellow
    $originalDir = Get-Location
    try {
        Set-Location $ProjectDir
        docker build -t ai-companion .
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ 镜像构建完成" -ForegroundColor Green
        } else {
            Write-Host "❌ 镜像构建失败" -ForegroundColor Red
            return
        }
    } finally {
        Set-Location $originalDir
    }

    Write-Host ""
    Write-Host "📁 创建配置目录..." -ForegroundColor Yellow
    $userDir = "$env:USERPROFILE\.ai-companion"
    New-Item -ItemType Directory -Path "$userDir\config" -Force | Out-Null
    New-Item -ItemType Directory -Path "$userDir\data" -Force | Out-Null
    Write-Host "✓ 配置目录: $userDir" -ForegroundColor Green

    Write-Host ""
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "✓ Docker 安装完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "下一步:" -ForegroundColor White
    Write-Host "  1. 配置 API Key（编辑 docker-compose.yml 或设置环境变量）" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  2. 启动服务:" -ForegroundColor Yellow
    Write-Host "     docker-compose up -d" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  3. 查看日志:" -ForegroundColor Yellow
    Write-Host "     docker-compose logs -f" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  配置目录: $userDir" -ForegroundColor Gray
    Write-Host "  配置文件: $userDir\config\" -ForegroundColor Gray
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
}

# 主流程
$ProjectDir = $PSScriptRoot

if ($IsOnlineInstall) {
    # 在线安装：下载项目到本地AppData目录
    $InstallDir = "$env:LOCALAPPDATA\AICompanion"
    Write-Host "📦 在线安装模式" -ForegroundColor Cyan
    Write-Host "   安装目录: $InstallDir" -ForegroundColor Gray
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

# 清理临时文件（仅在线安装）
if ($IsOnlineInstall -and (Test-Path "$env:TEMP\ai-girl-friend")) {
    Remove-Item -Path "$env:TEMP\ai-girl-friend" -Recurse -Force -ErrorAction SilentlyContinue
}
if ($IsOnlineInstall -and (Test-Path "$env:TEMP\ai-companion.zip")) {
    Remove-Item -Path "$env:TEMP\ai-companion.zip" -Force -ErrorAction SilentlyContinue
}
