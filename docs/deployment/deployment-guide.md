# 部署指南

## 概述

本文档详细介绍网络拨测平台的部署方法，包括单机部署、集群部署、容器化部署等多种方案。支持开发、测试、生产等不同环境的部署需求。

## 系统要求

### 硬件要求

**管理平台**：
- CPU: 4核心以上
- 内存: 8GB以上
- 存储: 100GB以上SSD
- 网络: 1Gbps带宽

**代理节点**：
- CPU: 2核心以上
- 内存: 2GB以上
- 存储: 20GB以上
- 网络: 100Mbps带宽

### 软件要求

**操作系统**：
- Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
- macOS 11+ (开发环境)
- Windows 10+ (开发环境)

**依赖软件**：
- Python 3.11+
- Node.js 16+
- Docker 20.10+
- Docker Compose 2.0+

**数据库**：
- PostgreSQL 13+
- Redis 6.0+
- RabbitMQ 3.8+

## 快速部署

### Docker Compose部署（推荐）

#### 1. 下载部署文件

```bash
# 克隆项目
git clone https://github.com/company/network-probe-platform.git
cd network-probe-platform

# 或者只下载部署文件
curl -O https://raw.githubusercontent.com/company/network-probe-platform/main/deployment/docker-compose.yml
curl -O https://raw.githubusercontent.com/company/network-probe-platform/main/deployment/.env.example
```

#### 2. 配置环境变量

```bash
# 复制环境配置文件
cp deployment/.env.example deployment/.env

# 编辑配置文件
vim deployment/.env
```

关键配置项：

```env
# 基础配置
COMPOSE_PROJECT_NAME=network-probe
ENVIRONMENT=production

# 数据库配置
POSTGRES_DB=network_probe
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
DATABASE_URL=postgresql://postgres:your_secure_password@postgres:5432/network_probe

# Redis配置
REDIS_PASSWORD=your_redis_password
REDIS_URL=redis://:your_redis_password@redis:6379/0

# RabbitMQ配置
RABBITMQ_DEFAULT_USER=admin
RABBITMQ_DEFAULT_PASS=your_rabbitmq_password
RABBITMQ_URL=amqp://admin:your_rabbitmq_password@rabbitmq:5672/

# JWT配置
JWT_SECRET_KEY=your_jwt_secret_key_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# 邮件配置
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@network-probe.com

# SSL证书配置
SSL_CERT_PATH=/etc/ssl/certs/server.crt
SSL_KEY_PATH=/etc/ssl/private/server.key

# 监控配置
PROMETHEUS_ENABLED=true
GRAFANA_ADMIN_PASSWORD=your_grafana_password
```

#### 3. 启动服务

```bash
# 启动所有服务
docker-compose -f deployment/docker-compose.yml up -d

# 查看服务状态
docker-compose -f deployment/docker-compose.yml ps

# 查看日志
docker-compose -f deployment/docker-compose.yml logs -f
```

#### 4. 初始化数据库

```bash
# 运行数据库迁移
docker-compose -f deployment/docker-compose.yml exec management python -m alembic upgrade head

# 创建管理员用户
docker-compose -f deployment/docker-compose.yml exec management python scripts/create_admin.py
```

#### 5. 验证部署

```bash
# 检查API健康状态
curl http://localhost:8000/api/v1/health

# 访问Web界面
open http://localhost:3000

# 检查监控面板
open http://localhost:3001  # Grafana
```

### 生产环境部署

#### 1. 使用生产配置

```bash
# 使用生产环境配置
docker-compose -f deployment/docker-compose.yml -f deployment/docker-compose.prod.yml up -d
```

#### 2. 配置反向代理

**Nginx配置示例**：

```nginx
# /etc/nginx/sites-available/network-probe
upstream management_backend {
    server 127.0.0.1:8000;
}

upstream web_frontend {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/ssl/certs/your-domain.crt;
    ssl_certificate_key /etc/ssl/private/your-domain.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;

    # API代理
    location /api/ {
        proxy_pass http://management_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket代理
    location /ws {
        proxy_pass http://management_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 前端代理
    location / {
        proxy_pass http://web_frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 静态文件缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        proxy_pass http://web_frontend;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/network-probe /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Kubernetes部署

### 1. 准备Kubernetes集群

```bash
# 检查集群状态
kubectl cluster-info
kubectl get nodes

# 创建命名空间
kubectl create namespace network-probe
```

### 2. 配置存储

**持久卷配置**：

```yaml
# deployment/kubernetes/pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: network-probe
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: fast-ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-pvc
  namespace: network-probe
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: fast-ssd
```

### 3. 配置密钥

```bash
# 创建数据库密钥
kubectl create secret generic postgres-secret \
  --from-literal=username=postgres \
  --from-literal=password=your_secure_password \
  --namespace=network-probe

# 创建Redis密钥
kubectl create secret generic redis-secret \
  --from-literal=password=your_redis_password \
  --namespace=network-probe

# 创建JWT密钥
kubectl create secret generic jwt-secret \
  --from-literal=secret-key=your_jwt_secret_key \
  --namespace=network-probe

# 创建SMTP密钥
kubectl create secret generic smtp-secret \
  --from-literal=username=your-email@gmail.com \
  --from-literal=password=your-app-password \
  --namespace=network-probe
```

### 4. 部署数据库

```yaml
# deployment/kubernetes/postgres.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: network-probe
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:13
        env:
        - name: POSTGRES_DB
          value: network_probe
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: network-probe
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
```

### 5. 部署管理平台

```yaml
# deployment/kubernetes/management.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: management
  namespace: network-probe
spec:
  replicas: 3
  selector:
    matchLabels:
      app: management
  template:
    metadata:
      labels:
        app: management
    spec:
      containers:
      - name: management
        image: network-probe/management:latest
        env:
        - name: DATABASE_URL
          value: postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@postgres:5432/network_probe
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        - name: REDIS_URL
          value: redis://:$(REDIS_PASSWORD)@redis:6379/0
        - name: REDIS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: redis-secret
              key: password
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: jwt-secret
              key: secret-key
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: management
  namespace: network-probe
spec:
  selector:
    app: management
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

### 6. 配置Ingress

```yaml
# deployment/kubernetes/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: network-probe-ingress
  namespace: network-probe
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  tls:
  - hosts:
    - your-domain.com
    secretName: network-probe-tls
  rules:
  - host: your-domain.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: management
            port:
              number: 8000
      - path: /ws
        pathType: Prefix
        backend:
          service:
            name: management
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: web
            port:
              number: 3000
```

### 7. 部署脚本

```bash
#!/bin/bash
# deployment/kubernetes/deploy-k8s.sh

set -e

echo "Deploying Network Probe Platform to Kubernetes..."

# 创建命名空间
kubectl apply -f namespace.yaml

# 部署存储
kubectl apply -f pvc.yaml

# 部署数据库
kubectl apply -f postgres.yaml
kubectl apply -f redis.yaml
kubectl apply -f rabbitmq.yaml

# 等待数据库就绪
echo "Waiting for databases to be ready..."
kubectl wait --for=condition=ready pod -l app=postgres --timeout=300s -n network-probe
kubectl wait --for=condition=ready pod -l app=redis --timeout=300s -n network-probe

# 运行数据库迁移
kubectl run migration --image=network-probe/management:latest --rm -i --restart=Never \
  --env="DATABASE_URL=postgresql://postgres:password@postgres:5432/network_probe" \
  --command -- python -m alembic upgrade head \
  -n network-probe

# 部署应用
kubectl apply -f management.yaml
kubectl apply -f web.yaml

# 配置网络
kubectl apply -f ingress.yaml

# 等待部署完成
kubectl wait --for=condition=available deployment/management --timeout=300s -n network-probe
kubectl wait --for=condition=available deployment/web --timeout=300s -n network-probe

echo "Deployment completed successfully!"
echo "Access the application at: https://your-domain.com"
```

## 代理部署

### 1. 单机代理部署

```bash
# 下载代理程序
wget https://releases.network-probe.com/agent/latest/network-probe-agent-linux-amd64.tar.gz
tar -xzf network-probe-agent-linux-amd64.tar.gz
cd network-probe-agent

# 配置代理
cp config/config.example.yaml config/config.yaml
vim config/config.yaml
```

代理配置示例：

```yaml
# config/config.yaml
server:
  url: "wss://your-domain.com/ws"
  reconnect_interval: 30
  heartbeat_interval: 60

agent:
  id: "agent-001"
  name: "Beijing-Agent-01"
  location:
    country: "China"
    city: "Beijing"
    latitude: 39.9042
    longitude: 116.4074
  isp: "China Telecom"

security:
  cert_file: "/etc/network-probe/client.crt"
  key_file: "/etc/network-probe/client.key"
  ca_file: "/etc/network-probe/ca.crt"

logging:
  level: "INFO"
  file: "/var/log/network-probe/agent.log"
  max_size: 100  # MB
  max_files: 10

protocols:
  enabled: ["icmp", "tcp", "udp", "http", "https"]
  
resources:
  max_concurrent_tasks: 10
  resource_report_interval: 300
```

### 2. 系统服务配置

```bash
# 创建系统用户
sudo useradd -r -s /bin/false network-probe

# 创建目录
sudo mkdir -p /opt/network-probe
sudo mkdir -p /etc/network-probe
sudo mkdir -p /var/log/network-probe

# 复制文件
sudo cp -r * /opt/network-probe/
sudo cp config/config.yaml /etc/network-probe/
sudo chown -R network-probe:network-probe /opt/network-probe
sudo chown -R network-probe:network-probe /var/log/network-probe

# 创建systemd服务
sudo tee /etc/systemd/system/network-probe-agent.service > /dev/null <<EOF
[Unit]
Description=Network Probe Agent
After=network.target

[Service]
Type=simple
User=network-probe
Group=network-probe
WorkingDirectory=/opt/network-probe
ExecStart=/opt/network-probe/agent --config /etc/network-probe/config.yaml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable network-probe-agent
sudo systemctl start network-probe-agent
sudo systemctl status network-probe-agent
```

### 3. 容器化代理部署

```dockerfile
# Dockerfile.agent
FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ ./agent/
COPY shared/ ./shared/

USER 1000:1000

CMD ["python", "-m", "agent"]
```

```yaml
# docker-compose.agent.yml
version: '3.8'

services:
  agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
    environment:
      - SERVER_URL=wss://your-domain.com/ws
      - AGENT_ID=agent-docker-001
      - AGENT_NAME=Docker-Agent-01
    volumes:
      - ./agent/config:/app/config:ro
      - ./certs:/app/certs:ro
    restart: unless-stopped
    network_mode: host
```

### 4. 批量代理部署

```bash
#!/bin/bash
# scripts/deploy-agents.sh

SERVERS=(
    "server1.example.com"
    "server2.example.com"
    "server3.example.com"
)

AGENT_PACKAGE="network-probe-agent-linux-amd64.tar.gz"
CONFIG_TEMPLATE="config/agent-template.yaml"

for server in "${SERVERS[@]}"; do
    echo "Deploying agent to $server..."
    
    # 上传文件
    scp $AGENT_PACKAGE root@$server:/tmp/
    scp $CONFIG_TEMPLATE root@$server:/tmp/config.yaml
    
    # 远程执行部署
    ssh root@$server << 'EOF'
        cd /tmp
        tar -xzf network-probe-agent-linux-amd64.tar.gz
        
        # 安装代理
        sudo mkdir -p /opt/network-probe
        sudo cp -r network-probe-agent/* /opt/network-probe/
        sudo cp config.yaml /etc/network-probe/
        
        # 配置服务
        sudo systemctl enable network-probe-agent
        sudo systemctl start network-probe-agent
        
        # 清理临时文件
        rm -rf /tmp/network-probe-agent*
EOF
    
    echo "Agent deployed to $server successfully"
done
```

## 监控配置

### 1. Prometheus配置

```yaml
# deployment/monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "rules/*.yml"

scrape_configs:
  - job_name: 'network-probe-management'
    static_configs:
      - targets: ['management:8000']
    metrics_path: '/metrics'
    scrape_interval: 30s

  - job_name: 'network-probe-agents'
    consul_sd_configs:
      - server: 'consul:8500'
        services: ['network-probe-agent']
    relabel_configs:
      - source_labels: [__meta_consul_service_address]
        target_label: __address__
        replacement: '${1}:9090'

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

### 2. Grafana仪表板

```json
{
  "dashboard": {
    "title": "Network Probe Platform",
    "panels": [
      {
        "title": "Active Tasks",
        "type": "stat",
        "targets": [
          {
            "expr": "network_probe_active_tasks_total",
            "legendFormat": "Active Tasks"
          }
        ]
      },
      {
        "title": "Task Success Rate",
        "type": "stat",
        "targets": [
          {
            "expr": "rate(network_probe_task_success_total[5m]) / rate(network_probe_task_total[5m]) * 100",
            "legendFormat": "Success Rate %"
          }
        ]
      },
      {
        "title": "Response Time",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(network_probe_task_duration_seconds_bucket[5m]))",
            "legendFormat": "95th percentile"
          },
          {
            "expr": "histogram_quantile(0.50, rate(network_probe_task_duration_seconds_bucket[5m]))",
            "legendFormat": "50th percentile"
          }
        ]
      }
    ]
  }
}
```

### 3. 告警规则

```yaml
# deployment/monitoring/rules/alerts.yml
groups:
  - name: network-probe
    rules:
      - alert: HighTaskFailureRate
        expr: rate(network_probe_task_failed_total[5m]) / rate(network_probe_task_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High task failure rate detected"
          description: "Task failure rate is {{ $value | humanizePercentage }} for the last 5 minutes"

      - alert: AgentDown
        expr: up{job="network-probe-agents"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Agent {{ $labels.instance }} is down"
          description: "Agent {{ $labels.instance }} has been down for more than 1 minute"

      - alert: DatabaseConnectionFailure
        expr: network_probe_database_connections_failed_total > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database connection failures detected"
          description: "{{ $value }} database connection failures in the last minute"

      - alert: HighMemoryUsage
        expr: (network_probe_memory_usage_bytes / network_probe_memory_total_bytes) * 100 > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          description: "Memory usage is {{ $value | humanizePercentage }} on {{ $labels.instance }}"
```

## 备份和恢复

### 1. 数据库备份

```bash
#!/bin/bash
# scripts/backup-database.sh

BACKUP_DIR="/backup/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="network_probe_backup_$DATE.sql"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
docker exec postgres pg_dump -U postgres network_probe > $BACKUP_DIR/$BACKUP_FILE

# 压缩备份文件
gzip $BACKUP_DIR/$BACKUP_FILE

# 删除7天前的备份
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Database backup completed: $BACKUP_FILE.gz"
```

### 2. 配置备份

```bash
#!/bin/bash
# scripts/backup-config.sh

BACKUP_DIR="/backup/config"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份配置文件
tar -czf $BACKUP_DIR/config_backup_$DATE.tar.gz \
    /etc/network-probe/ \
    /opt/network-probe/config/ \
    deployment/.env

echo "Configuration backup completed: config_backup_$DATE.tar.gz"
```

### 3. 恢复脚本

```bash
#!/bin/bash
# scripts/restore-database.sh

if [ $# -ne 1 ]; then
    echo "Usage: $0 <backup_file>"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "Restoring database from $BACKUP_FILE..."

# 停止应用服务
docker-compose stop management

# 解压备份文件（如果是压缩的）
if [[ $BACKUP_FILE == *.gz ]]; then
    gunzip -c $BACKUP_FILE | docker exec -i postgres psql -U postgres -d network_probe
else
    docker exec -i postgres psql -U postgres -d network_probe < $BACKUP_FILE
fi

# 重启应用服务
docker-compose start management

echo "Database restore completed"
```

### 4. 自动备份配置

```bash
# 添加到crontab
crontab -e

# 每天凌晨2点备份数据库
0 2 * * * /opt/network-probe/scripts/backup-database.sh

# 每周日凌晨3点备份配置
0 3 * * 0 /opt/network-probe/scripts/backup-config.sh

# 每月1号清理旧日志
0 4 1 * * find /var/log/network-probe -name "*.log" -mtime +30 -delete
```

## 安全配置

### 1. SSL/TLS证书

```bash
# 使用Let's Encrypt获取证书
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo crontab -e
0 12 * * * /usr/bin/certbot renew --quiet
```

### 2. 防火墙配置

```bash
# Ubuntu/Debian
sudo ufw enable
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8000/tcp  # API (内部)
sudo ufw deny 5432/tcp   # PostgreSQL (仅内部访问)
sudo ufw deny 6379/tcp   # Redis (仅内部访问)

# CentOS/RHEL
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 安全加固

```bash
# 禁用root SSH登录
sudo sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# 配置fail2ban
sudo apt install fail2ban
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# 配置自动更新
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## 性能优化

### 1. 数据库优化

```sql
-- PostgreSQL配置优化
-- /etc/postgresql/13/main/postgresql.conf

# 内存配置
shared_buffers = 256MB
effective_cache_size = 1GB
work_mem = 4MB
maintenance_work_mem = 64MB

# 连接配置
max_connections = 200
shared_preload_libraries = 'pg_stat_statements'

# 日志配置
log_statement = 'all'
log_duration = on
log_min_duration_statement = 1000

# 性能配置
random_page_cost = 1.1
effective_io_concurrency = 200
```

### 2. Redis优化

```conf
# /etc/redis/redis.conf

# 内存配置
maxmemory 512mb
maxmemory-policy allkeys-lru

# 持久化配置
save 900 1
save 300 10
save 60 10000

# 网络配置
tcp-keepalive 300
timeout 0

# 安全配置
requirepass your_redis_password
```

### 3. 应用优化

```python
# 数据库连接池配置
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

# Redis连接池配置
import redis.connection

redis_pool = redis.ConnectionPool(
    host='redis',
    port=6379,
    password='your_redis_password',
    db=0,
    max_connections=50,
    socket_keepalive=True,
    socket_keepalive_options={}
)
```

## 故障排除

### 常见问题

#### 1. 服务启动失败

```bash
# 检查日志
docker-compose logs management
docker-compose logs postgres

# 检查端口占用
sudo netstat -tlnp | grep :8000

# 检查磁盘空间
df -h

# 检查内存使用
free -h
```

#### 2. 数据库连接问题

```bash
# 测试数据库连接
docker exec -it postgres psql -U postgres -d network_probe

# 检查数据库状态
docker exec postgres pg_isready -U postgres

# 查看数据库日志
docker logs postgres
```

#### 3. 代理连接问题

```bash
# 检查代理日志
sudo journalctl -u network-probe-agent -f

# 测试WebSocket连接
wscat -c wss://your-domain.com/ws

# 检查证书
openssl s_client -connect your-domain.com:443 -servername your-domain.com
```

### 性能问题诊断

```bash
# 系统资源监控
htop
iotop
nethogs

# 数据库性能分析
docker exec postgres psql -U postgres -d network_probe -c "
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;"

# 应用性能分析
docker exec management python -m cProfile -o profile.stats -m management_platform.api.main
```

这个部署指南提供了完整的部署方案和运维指导，帮助运维人员成功部署和维护网络拨测平台。