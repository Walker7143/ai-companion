#!/bin/bash
#
# AI Companion 一键安装脚本
# 支持: macOS, Linux
#

set -e

echo "═══════════════════════════════════════════"
echo "  AI Companion 安装脚本"
echo "═══════════════════════════════════════════"
echo ""

# 检测 Python
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo "❌ 未检测到 Python 3.11+"
        echo "请先安装 Python: https://www.python.org/downloads/"
        exit 1
    fi

    VERSION=$($PYTHON_CMD --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$(echo "$VERSION < 3.11" | bc)" = "1" ]; then
        echo "❌ Python 版本过低: $VERSION (需要 3.11+)"
        echo "请升级 Python: https://www.python.org/downloads/"
        exit 1
    fi
    echo "✓ Python $VERSION"
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
    if [ "$(uname)" = "Darwin" ]; then
        USER_DIR="$HOME/ai-companion"
    else
        USER_DIR="$HOME/ai-companion"
    fi
}

# 主安装流程
main() {
    check_python
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
    echo "✓ 安装完成！"
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

main "$@"
