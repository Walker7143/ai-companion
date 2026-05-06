#!/bin/bash
# AI Companion — Embedding 一键安装脚本
# 用法: bash scripts/setup-embeddings.sh
#
# 功能：
# 1. 安装 sentence-transformers 和 Chroma
# 2. 下载 all-MiniLM-L6-v2 模型（约 90MB）
# 3. 自动将 config/models.yaml 的 embedding 设为 "local"
#
# 前置要求：
# - Python 3.8+
# - 约 500MB 硬盘空间
#
# 关闭功能：修改 config/models.yaml: embedding: "none"

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/config/models.yaml"

echo "━━━ AI Companion — Embedding 安装脚本 ━━━"
echo ""

# 1. 安装依赖
echo "[1/4] 安装 sentence-transformers 和 Chroma..."
if ! python -m pip show sentence-transformers chromadb > /dev/null 2>&1; then
    python -m pip install sentence-transformers chromadb -q
    echo "      ✓ 安装完成"
else
    echo "      ✓ 已安装（跳过）"
fi

# 2. 预下载模型
echo "[2/4] 下载模型 all-MiniLM-L6-v2（首次约 90MB）..."
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" 2>&1
echo "      ✓ 模型下载完成"

# 3. 修改配置
echo "[3/4] 更新配置文件..."
if [ -f "$CONFIG_FILE" ]; then
    # 检查是否已有 memory.embedding 配置
    if grep -q "embedding:" "$CONFIG_FILE"; then
        # 替换现有值
        sed -i '' 's/embedding: "[^"]*"/embedding: "local"/' "$CONFIG_FILE"
    else
        # 在 memory: 节点下添加（如果 memory 节点存在）
        if grep -q "^memory:" "$CONFIG_FILE"; then
            sed -i '' '/^memory:/a\  embedding: "local"\n  embedding_model: "all-MiniLM-L6-v2"' "$CONFIG_FILE"
        else
            # 在文件末尾追加
            echo "" >> "$CONFIG_FILE"
            echo "memory:" >> "$CONFIG_FILE"
            echo '  embedding: "local"' >> "$CONFIG_FILE"
            echo '  embedding_model: "all-MiniLM-L6-v2"' >> "$CONFIG_FILE"
        fi
    fi
    echo "      ✓ config/models.yaml 已更新为 embedding: \"local\""
else
    echo "      ⚠ config/models.yaml 不存在，跳过配置更新"
fi

# 4. 验证
echo "[4/4] 验证安装..."
python -c "from sentence_transformers import SentenceTransformer; m=SentenceTransformer('all-MiniLM-L6-v2'); print(f'      ✓ 模型加载成功，维度: {m.get_sentence_embedding_dimension()}')"

echo ""
echo "━━━ ✓ Embedding 安装完成 ━━━"
echo ""
echo "已启用本地向量模型："
echo "  - 无需 API Key，不花费用"
echo "  - 模型：all-MiniLM-L6-v2（384维）"
echo "  - 存储路径：~/.cache/huggingface/"
echo ""
echo "如需关闭，修改 config/models.yaml: embedding: \"none\""
