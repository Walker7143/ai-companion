# AI Companion 一键安装脚本
# 支持: Windows PowerShell

$ErrorActionPreference = "Stop"

Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  AI Companion 安装脚本" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

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

# 主安装流程
function Install-AICompanion {
    # Python 检查
    if (-not (Test-Python)) { return }

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
        Copy-Item "config\bots.yaml.example" "$userDir\config\bots.yaml" -ErrorAction SilentlyContinue
        Copy-Item "config\models.yaml.example" "$userDir\config\models.yaml" -ErrorAction SilentlyContinue
        Write-Host "✓ 配置文件已创建" -ForegroundColor Green
    }

    # 安装依赖
    Write-Host ""
    Write-Host "📦 安装 Python 依赖..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt -q
    Write-Host "✓ 依赖安装完成" -ForegroundColor Green

    Write-Host ""
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "✓ 安装完成！" -ForegroundColor Green
    Write-Host ""
    Write-Host "下一步:" -ForegroundColor White
    Write-Host "  1. 配置 API Key:" -ForegroundColor Yellow
    Write-Host "     cp config/models.yaml.example config/models.yaml" -ForegroundColor Gray
    Write-Host "     # 编辑 config/models.yaml 填入你的 API Key" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  2. 启动:" -ForegroundColor Yellow
    Write-Host "     python -m ai_companion start" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  配置目录: $userDir" -ForegroundColor Gray
    Write-Host "═══════════════════════════════════════════" -ForegroundColor Cyan
}

Install-AICompanion
