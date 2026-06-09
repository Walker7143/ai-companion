#!/bin/bash
#
# AI Companion 一键安装引导程序
# 用于 curl | bash 远程执行（无需 git）
#
# 原理：下载项目压缩包到临时目录，解压后执行安装脚本
#

set -e

INSTALL_MODE="${1:-auto}"
case "$INSTALL_MODE" in
    -d|--docker) INSTALL_MODE="docker" ;;
    -l|--local) INSTALL_MODE="local" ;;
    ""|auto|docker|local) ;;
    -h|--help)
        echo "Usage: bash install-cn.sh [auto|local|docker|--local|--docker]"
        exit 0
        ;;
    *)
        echo "Unknown install mode: $INSTALL_MODE"
        exit 1
        ;;
esac
PYTHON_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"

echo "═══════════════════════════════════════════"
echo "  AI Companion 一键安装 (国内镜像)"
echo "═══════════════════════════════════════════"
echo ""

# 检测 Docker
check_docker() {
    if command -v docker &> /dev/null; then
        if docker info &> /dev/null 2>&1; then
            echo "✓ Docker 已就绪"
            return 0
        fi
    fi
    return 1
}

# 检测 Python
check_python() {
    PYTHON_CMD=""
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        return 1
    fi

    VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    if ! $PYTHON_CMD -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        return 1
    fi
    echo "✓ Python $VERSION"
    return 0
}

# 获取用户数据目录
get_user_dir() {
    USER_DIR="$HOME/.ai-companion"
}

register_gateway_autostart() {
    local python_exe="$1"
    echo ""
    echo "Registering Gateway autostart..."
    if "$python_exe" -m ai_companion.autostart; then
        echo "Gateway autostart registered"
    else
        echo "Warning: Gateway autostart registration failed"
    fi
}

# 本地安装
install_local() {
    echo ""
    echo "📦 本地安装模式 (清华镜像)"
    echo ""

    if ! check_python; then
        echo "❌ 未检测到 Python 3.11+"
        echo ""
        echo "请先安装 Python（推荐 anaconda）："
        echo "  macOS: brew install python"
        echo "  Linux: sudo apt install python3 python3-pip"
        echo ""
        echo "或使用 Docker 模式: bash $0 --docker"
        exit 1
    fi

    PYTHON_CMD="${PYTHON_CMD:-python3}"

    echo ""
    echo "📁 创建用户数据目录..."
    get_user_dir
    mkdir -p "$USER_DIR/data/bots"
    mkdir -p "$USER_DIR/logs"
    echo "✓ 数据目录: $USER_DIR"

    # 创建虚拟环境
    echo ""
    echo "📦 创建 Python 虚拟环境..."
    $PYTHON_CMD -m venv "$USER_DIR/.venv"
    VENV_PIP="$USER_DIR/.venv/bin/pip"
    $VENV_PIP install --upgrade pip -i "$PYTHON_INDEX" -q
    echo "✓ 虚拟环境已创建: $USER_DIR/.venv"

    echo ""
    echo "📦 安装项目依赖 (清华镜像)..."
    $VENV_PIP install aiohttp httpx lark-oapi pyyaml pydantic rich jieba python-dotenv aiosqlite chromadb sentence-transformers -i "$PYTHON_INDEX" -q

    echo "✓ 项目依赖安装完成"

    echo ""
    echo "📦 安装 AI Companion..."
    $VENV_PIP install --no-cache-dir "$PROJECT_DIR" -i "$PYTHON_INDEX" -q
    echo "✓ AI Companion 已安装"
    register_gateway_autostart "$USER_DIR/.venv/bin/python"

    echo ""
    echo "📦 预下载本地 embedding 模型..."
    if "$USER_DIR/.venv/bin/python" -m ai_companion.embedding_setup; then
        echo "✓ embedding 模型已缓存"
    else
        echo "⚠️  embedding 模型预下载失败（首次启动可能会等待模型下载）"
    fi

    # 复制 Bot 模板到数据目录（pip 不打包运行时数据）
    echo ""
    echo "📦 复制 Bot 人格模板..."
    if [ -d "$PROJECT_DIR/data/bots" ]; then
        mkdir -p "$USER_DIR/data/bots"
        cp -r "$PROJECT_DIR/data/bots"/* "$USER_DIR/data/bots/" 2>/dev/null || true
        echo "✓ Bot 模板已准备"
    fi

    # Install frontend UI dependencies
    if [ -f "$PROJECT_DIR/ai-companion-ui/package.json" ]; then
        echo ""
        echo "📦 安装前端 UI 依赖..."
        if command -v npm &> /dev/null; then
            if npm install --prefix "$PROJECT_DIR/ai-companion-ui" 2>/dev/null; then
                echo "✓ 前端依赖已安装"
            else
                echo "⚠️  前端依赖安装失败（管理后台需要手动 npm install）"
            fi
        else
            echo "⚠️  npm 未找到，跳过前端 UI（管理后台需要 npm）"
        fi
    fi

    echo ""
    echo "═══════════════════════════════════════════"
    echo "✓ 安装完成！"
    echo ""
    echo "下一步:"
    echo "  1. 运行配置向导:"
    echo "     source $USER_DIR/.venv/bin/activate"
    echo "     ai-companion setup"
    echo ""
    echo "  2. 启动:"
    echo "     ai-companion start"
    echo ""
    echo "  配置目录: $USER_DIR"
    echo "═══════════════════════════════════════════"
}

# Docker 安装
install_docker() {
    echo ""
    echo "🐳 Docker 安装模式"
    echo ""

    if ! check_docker; then
        echo "❌ 未检测到 Docker"
        echo "请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    echo ""
    echo "📦 构建 Docker 镜像..."
    docker build -t ai-companion "$PROJECT_DIR"
    echo "✓ 镜像构建完成"

    echo ""
    echo "📁 创建配置目录..."
    get_user_dir
    mkdir -p "$USER_DIR/config"
    mkdir -p "$USER_DIR/data"
    echo "✓ 配置目录: $USER_DIR"

    echo ""
    echo "═══════════════════════════════════════════"
    echo "✓ Docker 安装完成！"
    echo ""
    echo "下一步:"
    echo "  1. 配置 API Key（编辑 docker-compose.yml 或设置环境变量）"
    echo ""
    echo "  2. 启动服务:"
    echo "     docker-compose up -d"
    echo ""
    echo "  配置目录: $USER_DIR"
    echo "  配置文件: $USER_DIR/config/"
    echo "═══════════════════════════════════════════"
}

# ============================================
# 主流程：下载项目并执行安装
# ============================================

echo "📥 正在下载项目..."
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# GitHub 存档下载 URL
ARCHIVE_URL="https://github.com/Walker7143/ai-companion/archive/refs/heads/master.tar.gz"

if command -v curl &> /dev/null; then
    curl -fsSL "$ARCHIVE_URL" -o "$TEMP_DIR/project.tar.gz" || {
        echo "❌ 下载失败，请检查网络连接"
        exit 1
    }
elif command -v wget &> /dev/null; then
    wget -q "$ARCHIVE_URL" -O "$TEMP_DIR/project.tar.gz" || {
        echo "❌ 下载失败，请检查网络连接"
        exit 1
    }
else
    echo "❌ 需要 curl 或 wget"
    exit 1
fi

echo "📦 正在解压项目..."
mkdir -p "$TEMP_DIR/extracted"
tar -xzf "$TEMP_DIR/project.tar.gz" -C "$TEMP_DIR/extracted" || {
    echo "❌ 解压失败"
    exit 1
}

# 找到解压后的项目目录（GitHub 会创建一个带 commit hash 的子目录）
PROJECT_DIR=$(find "$TEMP_DIR/extracted" -mindepth 1 -maxdepth 1 -type d | head -1)

if [ -z "$PROJECT_DIR" ] || [ ! -f "$PROJECT_DIR/setup.py" ]; then
    echo "❌ 项目结构异常"
    exit 1
fi

echo "✓ 项目已准备就绪"

# 根据安装模式执行
case "$INSTALL_MODE" in
    docker)
        install_docker
        ;;
    local)
        install_local
        ;;
    auto)
        if check_docker; then
            echo ""
            echo "检测到 Docker，将使用 Docker 模式安装（推荐）"
            install_docker
        else
            echo ""
            echo "未检测到 Docker，将使用本地安装"
            install_local
        fi
        ;;
    *)
        echo "未知安装模式: $INSTALL_MODE"
        exit 1
        ;;
esac
