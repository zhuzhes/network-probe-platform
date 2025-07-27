#!/bin/bash

# 网络拨测平台开发环境设置脚本

set -e

echo "🚀 设置网络拨测平台开发环境..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ 需要Python $required_version或更高版本，当前版本: $python_version"
    exit 1
fi

echo "✅ Python版本检查通过: $python_version"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建Python虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 升级pip
echo "⬆️ 升级pip..."
pip install --upgrade pip

# 安装依赖
echo "📚 安装项目依赖..."
pip install -r requirements.txt

# 安装开发工具
echo "🛠️ 安装开发工具..."
pip install -e .

# 安装pre-commit钩子
echo "🪝 设置pre-commit钩子..."
pre-commit install

# 检查Docker
if command -v docker &> /dev/null; then
    echo "✅ Docker已安装"
    if ! docker info &> /dev/null; then
        echo "⚠️ Docker守护进程未运行，请启动Docker"
    fi
else
    echo "⚠️ Docker未安装，请安装Docker以使用容器功能"
fi

# 检查Docker Compose
if command -v docker-compose &> /dev/null; then
    echo "✅ Docker Compose已安装"
elif docker compose version &> /dev/null; then
    echo "✅ Docker Compose (plugin)已安装"
else
    echo "⚠️ Docker Compose未安装，请安装Docker Compose"
fi

# 创建环境配置文件
if [ ! -f ".env" ]; then
    echo "📝 创建环境配置文件..."
    cp deployment/.env.example .env
    echo "请编辑.env文件配置您的环境变量"
fi

# 设置数据库
echo "🗄️ 设置数据库..."
if command -v docker &> /dev/null && docker info &> /dev/null; then
    echo "启动开发数据库..."
    docker-compose -f deployment/docker-compose.dev.yml up -d postgres redis rabbitmq
    
    # 等待数据库启动
    echo "等待数据库启动..."
    sleep 10
    
    # 运行数据库迁移
    echo "运行数据库迁移..."
    alembic upgrade head
else
    echo "⚠️ 请手动设置数据库或启动Docker"
fi

# 运行测试
echo "🧪 运行测试以验证设置..."
pytest tests/unit/ -v --tb=short

echo ""
echo "🎉 开发环境设置完成！"
echo ""
echo "下一步："
echo "1. 编辑.env文件配置环境变量"
echo "2. 运行 'make dev-server' 启动开发服务器"
echo "3. 运行 'make run-agent' 启动代理"
echo "4. 访问 http://localhost:8000 查看API文档"
echo ""
echo "常用命令："
echo "  make help          - 查看所有可用命令"
echo "  make test          - 运行测试"
echo "  make lint          - 代码检查"
echo "  make format        - 格式化代码"
echo "  make docker-run-dev - 启动开发环境"
echo ""