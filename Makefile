.PHONY: help install dev-install test lint format clean build docker-build docker-run

# 默认目标
help:
	@echo "可用的命令:"
	@echo "  install      - 安装生产依赖"
	@echo "  dev-install  - 安装开发依赖"
	@echo "  test         - 运行测试"
	@echo "  lint         - 运行代码检查"
	@echo "  format       - 格式化代码"
	@echo "  clean        - 清理临时文件"
	@echo "  build        - 构建项目"
	@echo "  docker-build - 构建Docker镜像"
	@echo "  docker-run   - 运行Docker容器"

# 安装依赖
install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pip install -e .
	pre-commit install

# 测试
test:
	pytest tests/ -v --cov=management_platform --cov=agent --cov=shared

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-e2e:
	pytest tests/e2e/ -v

# 代码质量
lint:
	flake8 management_platform agent shared
	mypy management_platform agent shared
	bandit -r management_platform agent shared

format:
	black management_platform agent shared tests
	isort management_platform agent shared tests

# 清理
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# 构建
build:
	python -m build

# Docker
docker-build:
	docker build -t network-probe-platform:latest .

docker-build-agent:
	docker build -f agent/Dockerfile -t network-probe-agent:latest .

docker-run-dev:
	docker-compose -f deployment/docker-compose.dev.yml up -d

docker-run-prod:
	docker-compose -f deployment/docker-compose.prod.yml up -d

docker-stop:
	docker-compose -f deployment/docker-compose.dev.yml down
	docker-compose -f deployment/docker-compose.prod.yml down

# 数据库
db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1

db-migration:
	alembic revision --autogenerate -m "$(message)"

# 开发服务器
dev-server:
	uvicorn management_platform.api.main:app --reload --host 0.0.0.0 --port 8000

# 生产服务器
prod-server:
	gunicorn management_platform.api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 代理
run-agent:
	python -m agent.main

# 安全检查
security-check:
	bandit -r management_platform agent shared
	safety check

# 性能测试
perf-test:
	locust -f tests/performance/locustfile.py --host=http://localhost:8000