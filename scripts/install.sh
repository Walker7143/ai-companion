#!/bin/bash
#
# AI Companion 一键安装脚本
# 支持: macOS, Linux
#
# 用法:
#   ./install.sh          # 本地安装（默认）
#   ./install.sh --docker # Docker 安装
#   ./install.sh -d       # Docker 安装
#

set -e

INSTALL_MODE="local"

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--docker)
            INSTALL_MODE="docker"
            shift
            ;;
        -h|--help)
            echo "用法: $0 [-d|--docker] [-h|--help]"
            echo ""
            echo "选项:"
            echo "  -d, --docker    使用 Docker 方式安装"
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
echo "  AI Companion 安装脚本"
echo "═══════════════════════════════════════════"
echo ""

# 检测 Docker
check_docker() {
    if command -v docker &> /dev/null; then
        if docker info &> /dev/null; then
            echo "✓ Docker 已就绪"
            return 0
        else
            echo "⚠️  Docker 已安装但当前用户无权限"
            echo "   请运行: sudo dockerd 或将用户加入 docker 组"
            return 1
        fi
    else
        return 1
    fi
}

# 检测 Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "❌ 未检测到 Python 3.11+"
        echo "请先安装 Python: https://www.python.org/downloads/"
        return 1
    fi

    VERSION=$($PYTHON_CMD --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$(echo "$VERSION < 3.11" | bc)" = "1" ]; then
        echo "❌ Python 版本过低: $VERSION (需要 3.11+)"
        echo "请升级 Python: https://www.python.org/downloads/"
        return 1
    fi
    echo "✓ Python $VERSION"
    return 0
}

# 检测 pip
check_pip() {
    if ! $PYTHON_CMD -m pip --version &> /dev/null; then
        echo "📦 安装 pip..."
        $PYTHON_CMD -m ensurepip --upgrade
    fi
    echo "✓ pip 已就绪"
}

# 获取用户数据目录
get_user_dir() {
    USER_DIR="$HOME/ai-companion"
}

# 本地安装
install_local() {
    echo ""
    echo "📦 本地安装模式"
    echo ""

    if ! check_python; then
        echo "❌ 本地安装需要 Python 3.11+"
        echo "请安装 Python 或使用 Docker 模式: $0 --docker"
        exit 1
    fi
    check_pip

    echo ""
    echo "📁 创建用户数据目录..."
    get_user_dir
    mkdir -p "$USER_DIR/data/bots"
    mkdir -p "$USER_DIR/logs"
    echo "✓ 数据目录: $USER_DIR"

    echo ""
    echo "📦 安装依赖..."
    pip install -r requirements.txt --quiet
    echo "✓ 依赖安装完成"

    echo ""
    echo "⚙️  初始化配置..."
    if [ ! -f "$USER_DIR/config.yaml" ]; then
        mkdir -p "$USER_DIR/config"
        cp config/bots.yaml.example "$USER_DIR/config/bots.yaml" 2>/dev/null || true
        cp config/models.yaml.example "$USER_DIR/config/models.yaml" 2>/dev/null || true
        echo "✓ 配置文件已创建"
    fi

    echo ""
    echo "═══════════════════════════════════════════"
    echo "✓ 本地安装完成！"
    echo ""
    echo "下一步:"
    echo "  1. 配置 API Key:"
    echo "     cp config/models.yaml.example config/models.yaml"
    echo "     # 编辑 config/models.yaml 填入你的 API Key"
    echo ""
    echo "  2. 启动:"
    echo "     python -m ai_companion start"
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
esac
