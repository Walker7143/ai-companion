# AI Companion 一键安装脚本
# 支持: Windows PowerShell
#
# 用法:
#   .\install.ps1          # 本地安装（默认）
#   .\install.ps1 -Docker  # Docker 安装
#   .\install.ps1 -D       # Docker 安装

param(
    [switch]$D,
    [switch]$Docker
)

$ErrorActionPreference = "Stop"

$InstallMode = "local"
if ($D -or $Docker) {
    $InstallMode = "docker"
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

# 获取 pip 安装命令（处理 externally-managed-environment）
function Get-PipCommand {
    # pip 25+ 已移除 --break-system-packages，使用 --user 代替
    $testResult = & python -m pip install -e . --dry-run 2>&1
    if ($testResult -match "externally-managed-environment") {
        return "python -m pip install --user"
    }
    return "python -m pip install"
}

# 本地安装
function Install-Local {
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
    $pipCmd = Get-PipCommand

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
        Copy-Item "config\bots.yaml.example" "$userDir\config\bots.yaml" -ErrorAction SilentlyContinue
        Copy-Item "config\models.yaml.example" "$userDir\config\models.yaml" -ErrorAction SilentlyContinue
        Write-Host "✓ 配置文件已创建" -ForegroundColor Green
    }

    # 安装依赖
    Write-Host ""
    Write-Host "📦 安装 Python 依赖..." -ForegroundColor Yellow
    & python -m pip install -r requirements.txt -q
    Write-Host "✓ 依赖安装完成" -ForegroundColor Green

    # 安装 AI Companion（全局命令）
    Write-Host ""
    Write-Host "📦 安装 AI Companion（全局命令）..." -ForegroundColor Yellow
    $venvDir = "$userDir\.venv"
    $testResult = & python -m pip install -e . --dry-run 2>&1

    if ($testResult -match "externally-managed-environment") {
        Write-Host "   系统 Python 受保护，创建虚拟环境..." -ForegroundColor Yellow
        python -m venv $venvDir
        $venvPip = "$venvDir\Scripts\pip.exe"
        & $venvPip install --upgrade pip -q
        & $venvPip install -r requirements.txt -q
        & $venvPip install -e .
        Write-Host "✓ AI Companion 已安装到虚拟环境: $venvDir" -ForegroundColor Green
        Write-Host "   激活虚拟环境: $venvDir\Scripts\activate.bat" -ForegroundColor Gray
    } else {
        & python -m pip install -e .
        Write-Host "✓ AI Companion 命令已安装: ai-companion" -ForegroundColor Green
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
    Write-Host "     ai-companion setup" -ForegroundColor Gray
    Write-Host "     ai-companion start" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  配置目录: $userDir" -ForegroundColor Gray
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
}

# Docker 安装
function Install-Docker {
    Write-Host ""
    Write-Host "🐳 Docker 安装模式" -ForegroundColor Cyan
    Write-Host ""

    if (-not (Test-Docker)) {
        Write-Host ""
        Write-Host "请先安装 Docker: https://docs.docker.com/get-docker/" -ForegroundColor Yellow
        Write-Host "或使用本地安装模式: .\install.ps1" -ForegroundColor Yellow
        return
    }

    Write-Host ""
    Write-Host "📦 构建 Docker 镜像..." -ForegroundColor Yellow
    docker build -t ai-companion .
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ 镜像构建完成" -ForegroundColor Green
    } else {
        Write-Host "❌ 镜像构建失败" -ForegroundColor Red
        return
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
switch ($InstallMode) {
    "docker" { Install-Docker }
    "local"  { Install-Local }
}
