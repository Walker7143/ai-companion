#!/bin/bash
#
# AI Companion 一键安装脚本
# 支持: macOS, Linux, Windows (WSL)
#
# 用法:
#   ./install.sh          # 自动选择最佳安装方式
#   ./install.sh --docker # 强制使用 Docker
#   ./install.sh --local  # 强制本地安装（需要 Python 3.11+）
#

set -e

INSTALL_MODE="auto"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--docker)
            INSTALL_MODE="docker"
            shift
            ;;
        -l|--local)
            INSTALL_MODE="local"
            shift
            ;;
        -h|--help)
            echo "用法: $0 [-d|--docker] [-l|--local] [-h|--help]"
            echo ""
            echo "选项:"
            echo "  -d, --docker    使用 Docker 方式安装（推荐，最简单）"
            echo "  -l, --local     本地安装（需要 Python 3.11+）"
            echo "  -h, --help      显示帮助信息"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

echo "═══════════════════════════════════════════"
echo "  AI Companion 一键安装"
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

# 检测 Python（仅检测，不终止）
check_python_quiet() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        return 1
    fi

    VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    if [ "$(echo "$VERSION < 3.11" | bc 2>/dev/null || echo "1")" = "1" ]; then
        return 1
    fi
    return 0
}

# 检测 pip 是否可用（能正常安装包）
check_pip_works() {
    if $PYTHON_CMD -m pip list 2>&1 | grep -q "externally-managed-environment"; then
        return 1
    fi
    return 0
}

# 获取用户数据目录
get_user_dir() {
    USER_DIR="$HOME/.ai-companion"
}

# 本地安装
install_local() {
    PYTHON_CMD=""
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    fi

    echo ""
    echo "📦 本地安装模式"
    echo ""

    if [ -z "$PYTHON_CMD" ]; then
        echo "❌ 未检测到 Python 3.11+"
        echo ""
        echo "请先安装 Python（推荐 anaconda）："
        echo "  macOS: brew install python"
        echo "  Linux: sudo apt install python3 python3-pip"
        echo "  Windows: 下载 https://www.python.org/downloads/"
        echo ""
        echo "或使用 Docker 模式: $0 --docker"
        exit 1
    fi

    VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    if [ "$(echo "$VERSION < 3.11" | bc 2>/dev/null || echo "1")" = "1" ]; then
        echo "❌ Python 版本过低: $VERSION (需要 3.11+)"
        echo "请升级 Python: https://www.python.org/downloads/"
        exit 1
    fi
    echo "✓ Python $VERSION"

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
    $VENV_PIP install --upgrade pip -q
    echo "✓ 虚拟环境已创建: $USER_DIR/.venv"

    echo ""
    echo "📦 安装项目依赖..."

    # Install core dependencies first (these don't need compilation)
    $VENV_PIP install aiohttp httpx lark-oapi pyyaml pydantic rich jieba python-dotenv sentence-transformers -q

    # Try chroma-hnswlib with binary wheel (may fail on some platforms without C++ compiler)
    echo "  Attempting chroma-hnswlib (vector search)..."
    if $VENV_PIP install chroma-hnswlib aiosqlite --only-binary :all: -q 2>/dev/null; then
        echo "✓ chroma-hnswlib installed"
    else
        echo "⚠️  chroma-hnswlib skipped (vector search disabled)"
    fi

    echo "✓ 项目依赖安装完成"

    echo ""
    echo "📦 安装 AI Companion..."
    $VENV_PIP install -e .
    echo "✓ AI Companion 已安装"

    # Install frontend UI dependencies (for management dashboard)
    if [ -f "$PROJECT_DIR/ai-companion-ui/package.json" ]; then
        echo ""
        echo "📦 安装前端 UI 依赖..."
        if command -v npm &> /dev/null; then
            if npm install --prefix "$PROJECT_DIR/ai-companion-ui"; then
                echo "✓ 前端依赖已安装"
            else
                echo "⚠️  前端依赖安装失败（管理后台需要手动 npm install）"
            fi
        else
            echo "⚠️  npm 未找到，跳过前端 UI（管理后台需要 npm）"
        fi
    fi

    echo ""
    echo "⚙️  初始化配置..."
    if [ ! -f "$USER_DIR/config/models.yaml" ]; then
        mkdir -p "$USER_DIR/config"
        cp config/bots.yaml.example "$USER_DIR/config/bots.yaml" 2>/dev/null || true
        cp config/models.yaml.example "$USER_DIR/config/models.yaml" 2>/dev/null || true
        echo "✓ 配置文件已创建"
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
        echo ""
        echo "或使用本地安装模式: $0"
        exit 1
    fi

    echo ""
    echo "📦 构建 Docker 镜像..."
    docker build -t ai-companion .
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
    echo "  1. 配置 API Key（编辑 docker-compose.yml 或设置环境变量）:"
    echo "     # 在 docker-compose.yml 中设置环境变量"
    echo "     environment:"
    echo "       - MINIMAX_API_KEY=your_api_key"
    echo ""
    echo "  2. 启动服务:"
    echo "     docker-compose up -d"
    echo ""
    echo "  3. 查看日志:"
    echo "     docker-compose logs -f"
    echo ""
    echo "  配置目录: $USER_DIR"
    echo "  配置文件: $USER_DIR/config/"
    echo "═══════════════════════════════════════════"
}

# 主流程
case $INSTALL_MODE in
    docker)
        install_docker
        ;;
    local)
        install_local
        ;;
    auto)
        # 自动选择：优先 Docker，否则本地
        if check_docker; then
            echo "检测到 Docker，将使用 Docker 模式安装（推荐）"
            echo ""
            install_docker
        else
            echo "未检测到 Docker 或无权限，将使用本地安装"
            echo ""
            install_local
        fi
        ;;
esac
