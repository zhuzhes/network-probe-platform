# 网络拨测平台

一个基于Python的分布式网络拨测平台，用于监控和测试网络连接质量和可用性。

## 项目概述

网络拨测平台是一个SaaS服务，由中央管理服务器和分布在各种VPS上的代理组成。平台支持多种网络协议的拨测，提供安全的通信机制，并为企业用户提供完整的网络监控解决方案。

## 主要特性

- **多协议支持**: ICMP、TCP、UDP、HTTP/HTTPS等协议的拨测
- **分布式架构**: 中央管理平台 + 分布式代理节点
- **安全通信**: TLS加密通信，代理不对外开放端口
- **智能调度**: 基于负载、位置和性能的智能任务分配
- **企业级功能**: 用户管理、计费系统、API接口
- **容器化部署**: 支持Docker和Kubernetes部署
- **OTA更新**: 代理远程更新和管理

## 项目结构

```
network-probe-platform/
├── management-platform/    # 管理平台
│   ├── api/               # API服务
│   ├── web/               # Web界面
│   ├── scheduler/         # 任务调度器
│   └── database/          # 数据库相关
├── agent/                 # 代理程序
│   ├── core/              # 核心功能
│   ├── protocols/         # 协议实现
│   ├── monitoring/        # 资源监控
│   └── updater/           # OTA更新
├── shared/                # 共享组件
│   ├── models/            # 数据模型
│   ├── utils/             # 工具函数
│   └── security/          # 安全组件
├── docs/                  # 文档
├── tests/                 # 测试
└── deployment/            # 部署配置
```

## 快速开始

### 环境要求

- Python 3.9+
- Docker & Docker Compose
- PostgreSQL 13+
- Redis 6+
- RabbitMQ 3.8+

### 开发环境设置

1. 克隆项目
```bash
git clone <repository-url>
cd network-probe-platform
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 启动开发环境
```bash
docker-compose -f deployment/docker-compose.dev.yml up -d
```

### 生产部署

使用Docker Compose:
```bash
docker-compose -f deployment/docker-compose.prod.yml up -d
```

使用Kubernetes:
```bash
kubectl apply -f deployment/k8s/
```

## 开发指南

### 代码规范

- 使用Black进行代码格式化
- 使用flake8进行代码检查
- 使用mypy进行类型检查
- 遵循PEP 8编码规范

### 测试

运行单元测试:
```bash
pytest tests/unit/
```

运行集成测试:
```bash
pytest tests/integration/
```

运行端到端测试:
```bash
pytest tests/e2e/
```

### 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## API文档

API文档可在以下地址访问:
- 开发环境: http://localhost:8000/docs
- 生产环境: https://your-domain.com/docs

## 许可证

本项目采用MIT许可证 - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- 项目主页: https://github.com/your-org/network-probe-platform
- 问题反馈: https://github.com/your-org/network-probe-platform/issues
- 邮箱: support@your-domain.com