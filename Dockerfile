# AI Companion Dockerfile
# 支持本地安装和 Docker 两种部署方式

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（用于 jieba 等需要编译的包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 默认启动 gateway（可覆盖）
CMD ["python", "-m", "ai_companion", "gateway", "start", "--sync"]
