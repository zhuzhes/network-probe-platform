# 监控和维护指南

## 概述

本文档详细介绍网络拨测平台的监控体系、维护流程和最佳实践。通过完善的监控和维护机制，确保系统稳定运行和最佳性能。

## 监控架构

### 监控体系概览

```mermaid
graph TB
    subgraph "应用层监控"
        A[管理平台] --> B[Prometheus]
        C[代理节点] --> B
        D[Web界面] --> B
    end
    
    subgraph "基础设施监控"
        E[服务器] --> F[Node Exporter]
        G[数据库] --> H[Postgres Exporter]
        I[Redis] --> J[Redis Exporter]
        F --> B
        H --> B
        J --> B
    end
    
    subgraph "可视化和告警"
        B --> K[Grafana]
        B --> L[AlertManager]
        L --> M[邮件通知]
        L --> N[Slack通知]
        L --> O[PagerDuty]
    end
    
    subgraph "日志监控"
        P[应用日志] --> Q[Loki]
        R[系统日志] --> Q
        Q --> S[Grafana Logs]
    end
```

## 指标监控

### 1. 应用指标

#### 管理平台指标

```python
# management_platform/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info
import time
import functools

# 请求计数器
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

# 请求延迟直方图
REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

# 活跃连接数
ACTIVE_CONNECTIONS = Gauge(
    'websocket_connections_active',
    'Active WebSocket connections'
)

# 任务指标
TASK_COUNTER = Counter(
    'tasks_total',
    'Total tasks executed',
    ['protocol', 'status']
)

TASK_DURATION = Histogram(
    'task_duration_seconds',
    'Task execution duration',
    ['protocol']
)

# 代理指标
AGENT_COUNT = Gauge(
    'agents_total',
    'Total number of agents',
    ['status']
)

AGENT_RESOURCE_USAGE = Gauge(
    'agent_resource_usage',
    'Agent resource usage',
    ['agent_id', 'resource_type']
)

# 数据库指标
DB_CONNECTIONS = Gauge(
    'database_connections_active',
    'Active database connections'
)

DB_QUERY_DURATION = Histogram(
    'database_query_duration_seconds',
    'Database query duration',
    ['operation']
)

# 系统信息
SYSTEM_INFO = Info(
    'system_info',
    'System information'
)

def monitor_requests(func):
    """请求监控装饰器"""
    @functools.wraps(func)
    async def wrapper(request, *args, **kwargs):
        method = request.method
        endpoint = request.url.path
        
        start_time = time.time()
        
        try:
            response = await func(request, *args, **kwargs)
            status = response.status_code
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
            return response
        except Exception as e:
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=500).inc()
            raise
        finally:
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                time.time() - start_time
            )
    
    return wrapper

def monitor_tasks(func):
    """任务监控装饰器"""
    @functools.wraps(func)
    async def wrapper(task, *args, **kwargs):
        protocol = task.protocol
        start_time = time.time()
        
        try:
            result = await func(task, *args, **kwargs)
            TASK_COUNTER.labels(protocol=protocol, status='success').inc()
            return result
        except Exception as e:
            TASK_COUNTER.labels(protocol=protocol, status='error').inc()
            raise
        finally:
            TASK_DURATION.labels(protocol=protocol).observe(
                time.time() - start_time
            )
    
    return wrapper
```

#### 代理指标

```python
# agent/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import psutil
import asyncio

# 任务执行指标
AGENT_TASK_COUNTER = Counter(
    'agent_tasks_total',
    'Total tasks executed by agent',
    ['protocol', 'status']
)

AGENT_TASK_DURATION = Histogram(
    'agent_task_duration_seconds',
    'Task execution duration on agent',
    ['protocol']
)

# 系统资源指标
CPU_USAGE = Gauge('agent_cpu_usage_percent', 'CPU usage percentage')
MEMORY_USAGE = Gauge('agent_memory_usage_bytes', 'Memory usage in bytes')
MEMORY_TOTAL = Gauge('agent_memory_total_bytes', 'Total memory in bytes')
DISK_USAGE = Gauge('agent_disk_usage_bytes', 'Disk usage in bytes')
DISK_TOTAL = Gauge('agent_disk_total_bytes', 'Total disk space in bytes')
NETWORK_SENT = Counter('agent_network_sent_bytes_total', 'Network bytes sent')
NETWORK_RECV = Counter('agent_network_recv_bytes_total', 'Network bytes received')

# 连接状态指标
CONNECTION_STATUS = Gauge('agent_connection_status', 'Connection status (1=connected, 0=disconnected)')
HEARTBEAT_COUNTER = Counter('agent_heartbeats_total', 'Total heartbeats sent')

class AgentMetricsCollector:
    def __init__(self):
        self.last_network_stats = psutil.net_io_counters()
    
    async def start_metrics_server(self, port=9090):
        """启动指标服务器"""
        start_http_server(port)
        
        # 启动资源监控循环
        asyncio.create_task(self.collect_system_metrics())
    
    async def collect_system_metrics(self):
        """收集系统指标"""
        while True:
            try:
                # CPU使用率
                cpu_percent = psutil.cpu_percent(interval=1)
                CPU_USAGE.set(cpu_percent)
                
                # 内存使用情况
                memory = psutil.virtual_memory()
                MEMORY_USAGE.set(memory.used)
                MEMORY_TOTAL.set(memory.total)
                
                # 磁盘使用情况
                disk = psutil.disk_usage('/')
                DISK_USAGE.set(disk.used)
                DISK_TOTAL.set(disk.total)
                
                # 网络统计
                network = psutil.net_io_counters()
                NETWORK_SENT.inc(network.bytes_sent - self.last_network_stats.bytes_sent)
                NETWORK_RECV.inc(network.bytes_recv - self.last_network_stats.bytes_recv)
                self.last_network_stats = network
                
            except Exception as e:
                print(f"Error collecting metrics: {e}")
            
            await asyncio.sleep(30)  # 每30秒收集一次
    
    def record_task_execution(self, protocol: str, duration: float, success: bool):
        """记录任务执行指标"""
        status = 'success' if success else 'error'
        AGENT_TASK_COUNTER.labels(protocol=protocol, status=status).inc()
        AGENT_TASK_DURATION.labels(protocol=protocol).observe(duration)
    
    def update_connection_status(self, connected: bool):
        """更新连接状态"""
        CONNECTION_STATUS.set(1 if connected else 0)
    
    def record_heartbeat(self):
        """记录心跳"""
        HEARTBEAT_COUNTER.inc()
```

### 2. 基础设施指标

#### Node Exporter配置

```yaml
# deployment/monitoring/node-exporter.yml
version: '3.8'

services:
  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    restart: unless-stopped
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.rootfs=/rootfs'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"
    networks:
      - monitoring
```

#### Postgres Exporter配置

```yaml
# deployment/monitoring/postgres-exporter.yml
version: '3.8'

services:
  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    container_name: postgres-exporter
    restart: unless-stopped
    environment:
      DATA_SOURCE_NAME: "postgresql://postgres:password@postgres:5432/network_probe?sslmode=disable"
    ports:
      - "9187:9187"
    networks:
      - monitoring
    depends_on:
      - postgres
```

#### Redis Exporter配置

```yaml
# deployment/monitoring/redis-exporter.yml
version: '3.8'

services:
  redis-exporter:
    image: oliver006/redis_exporter:latest
    container_name: redis-exporter
    restart: unless-stopped
    environment:
      REDIS_ADDR: "redis://redis:6379"
      REDIS_PASSWORD: "your_redis_password"
    ports:
      - "9121:9121"
    networks:
      - monitoring
    depends_on:
      - redis
```

## 日志监控

### 1. 日志收集配置

#### Loki配置

```yaml
# deployment/monitoring/loki.yml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: false
  retention_period: 0s

compactor:
  working_directory: /loki/boltdb-shipper-compactor
  shared_store: filesystem
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150

ingester:
  max_chunk_age: 1h
  chunk_idle_period: 3m
  chunk_block_size: 262144
  chunk_retain_period: 1m
  max_transfer_retries: 0
  wal:
    enabled: true
    dir: /loki/wal
  lifecycler:
    address: 127.0.0.1
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
    final_sleep: 0s
  chunk_encoding: snappy
```

#### Promtail配置

```yaml
# deployment/monitoring/promtail.yml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: management-platform
    static_configs:
      - targets:
          - localhost
        labels:
          job: management-platform
          __path__: /var/log/network-probe/management/*.log
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            message: message
            module: module
      - timestamp:
          source: timestamp
          format: RFC3339
      - labels:
          level:
          module:

  - job_name: agents
    static_configs:
      - targets:
          - localhost
        labels:
          job: agents
          __path__: /var/log/network-probe/agents/*.log
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            message: message
            agent_id: agent_id
      - timestamp:
          source: timestamp
          format: RFC3339
      - labels:
          level:
          agent_id:

  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          __path__: /var/log/nginx/*.log
    pipeline_stages:
      - regex:
          expression: '^(?P<remote_addr>\S+) - (?P<remote_user>\S+) \[(?P<time_local>[^\]]+)\] "(?P<method>\S+) (?P<request_uri>\S+) (?P<server_protocol>\S+)" (?P<status>\d+) (?P<body_bytes_sent>\d+) "(?P<http_referer>[^"]*)" "(?P<http_user_agent>[^"]*)"'
      - timestamp:
          source: time_local
          format: 02/Jan/2006:15:04:05 -0700
      - labels:
          method:
          status:
```

### 2. 日志分析查询

#### 常用LogQL查询

```logql
# 查看错误日志
{job="management-platform"} |= "ERROR"

# 按级别统计日志
sum by (level) (count_over_time({job="management-platform"}[1h]))

# 查看特定代理的日志
{job="agents", agent_id="agent-001"}

# 查看API错误率
sum(rate({job="management-platform"} |= "ERROR" [5m])) / sum(rate({job="management-platform"}[5m]))

# 查看慢查询
{job="management-platform"} |= "slow query" | json | duration > 1000

# 按时间范围查看日志
{job="management-platform"} | json | timestamp >= "2024-01-01T00:00:00Z" and timestamp <= "2024-01-01T23:59:59Z"
```

## 告警配置

### 1. AlertManager配置

```yaml
# deployment/monitoring/alertmanager.yml
global:
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alerts@network-probe.com'
  smtp_auth_username: 'alerts@network-probe.com'
  smtp_auth_password: 'your_app_password'

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'web.hook'
  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
    - match:
        severity: warning
      receiver: 'warning-alerts'

receivers:
  - name: 'web.hook'
    webhook_configs:
      - url: 'http://localhost:5001/'

  - name: 'critical-alerts'
    email_configs:
      - to: 'ops-team@company.com'
        subject: '[CRITICAL] Network Probe Alert'
        body: |
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}
    slack_configs:
      - api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
        channel: '#alerts'
        title: 'Critical Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'

  - name: 'warning-alerts'
    email_configs:
      - to: 'dev-team@company.com'
        subject: '[WARNING] Network Probe Alert'
        body: |
          {{ range .Alerts }}
          Alert: {{ .Annotations.summary }}
          Description: {{ .Annotations.description }}
          {{ end }}

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
```

### 2. 告警规则

```yaml
# deployment/monitoring/rules/network-probe.yml
groups:
  - name: network-probe-system
    rules:
      - alert: HighCPUUsage
        expr: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage on {{ $labels.instance }}"
          description: "CPU usage is above 80% for more than 5 minutes"

      - alert: HighMemoryUsage
        expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          description: "Memory usage is above 85% for more than 5 minutes"

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space on {{ $labels.instance }}"
          description: "Disk space is below 10%"

  - name: network-probe-application
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} for the last 5 minutes"

      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High response time detected"
          description: "95th percentile response time is {{ $value }}s"

      - alert: DatabaseConnectionFailure
        expr: database_connections_active == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database connection failure"
          description: "No active database connections"

      - alert: AgentDisconnected
        expr: agent_connection_status == 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Agent {{ $labels.agent_id }} disconnected"
          description: "Agent has been disconnected for more than 2 minutes"

      - alert: TaskFailureRateHigh
        expr: rate(tasks_total{status="error"}[5m]) / rate(tasks_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High task failure rate"
          description: "Task failure rate is {{ $value | humanizePercentage }}"

  - name: network-probe-business
    rules:
      - alert: LowTaskThroughput
        expr: rate(tasks_total[5m]) < 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low task throughput"
          description: "Task execution rate is below 10 tasks per second"

      - alert: UserCreditsLow
        expr: user_credits_balance < 100
        for: 1m
        labels:
          severity: info
        annotations:
          summary: "User {{ $labels.user_id }} has low credits"
          description: "User credits balance is {{ $value }}"
```

## 性能监控

### 1. 应用性能监控

#### APM集成

```python
# management_platform/monitoring/apm.py
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

def setup_tracing(app):
    """设置分布式追踪"""
    # 配置追踪提供者
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)
    
    # 配置Jaeger导出器
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )
    
    span_processor = BatchSpanProcessor(jaeger_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)
    
    # 自动仪表化
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    RedisInstrumentor().instrument()
    
    return tracer

# 使用示例
tracer = setup_tracing(app)

@tracer.start_as_current_span("create_task")
async def create_task(task_data: dict):
    with tracer.start_as_current_span("validate_task") as span:
        span.set_attribute("task.protocol", task_data["protocol"])
        # 验证逻辑
        
    with tracer.start_as_current_span("save_task"):
        # 保存逻辑
        pass
```

#### 性能分析

```python
# management_platform/monitoring/profiler.py
import cProfile
import pstats
import io
from functools import wraps

def profile_performance(func):
    """性能分析装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            pr.disable()
            
            # 生成性能报告
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats()
            
            # 记录到日志
            logger.info(f"Performance profile for {func.__name__}:\n{s.getvalue()}")
    
    return wrapper

# 内存使用监控
import tracemalloc
import asyncio

class MemoryMonitor:
    def __init__(self):
        self.snapshots = []
    
    async def start_monitoring(self):
        """开始内存监控"""
        tracemalloc.start()
        
        while True:
            snapshot = tracemalloc.take_snapshot()
            self.snapshots.append(snapshot)
            
            # 保留最近10个快照
            if len(self.snapshots) > 10:
                self.snapshots.pop(0)
            
            # 分析内存使用
            if len(self.snapshots) >= 2:
                self.analyze_memory_growth()
            
            await asyncio.sleep(300)  # 每5分钟检查一次
    
    def analyze_memory_growth(self):
        """分析内存增长"""
        current = self.snapshots[-1]
        previous = self.snapshots[-2]
        
        top_stats = current.compare_to(previous, 'lineno')
        
        for stat in top_stats[:10]:
            if stat.size_diff > 1024 * 1024:  # 超过1MB增长
                logger.warning(f"Memory growth detected: {stat}")
```

### 2. 数据库性能监控

```sql
-- 慢查询监控
SELECT 
    query,
    calls,
    total_time,
    mean_time,
    rows,
    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
FROM pg_stat_statements 
WHERE mean_time > 1000  -- 超过1秒的查询
ORDER BY total_time DESC 
LIMIT 20;

-- 锁等待监控
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement,
    blocking_activity.query AS current_statement_in_blocking_process
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.DATABASE IS NOT DISTINCT FROM blocked_locks.DATABASE
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.GRANTED;

-- 连接监控
SELECT 
    state,
    count(*) as connections
FROM pg_stat_activity 
GROUP BY state;
```

## 维护流程

### 1. 日常维护任务

#### 自动化维护脚本

```bash
#!/bin/bash
# scripts/daily-maintenance.sh

LOG_FILE="/var/log/network-probe/maintenance.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting daily maintenance..." >> $LOG_FILE

# 1. 清理旧日志
echo "[$DATE] Cleaning old logs..." >> $LOG_FILE
find /var/log/network-probe -name "*.log" -mtime +30 -delete
find /var/log/network-probe -name "*.log.*" -mtime +7 -delete

# 2. 清理临时文件
echo "[$DATE] Cleaning temporary files..." >> $LOG_FILE
find /tmp -name "network-probe-*" -mtime +1 -delete

# 3. 数据库维护
echo "[$DATE] Running database maintenance..." >> $LOG_FILE
docker exec postgres psql -U postgres -d network_probe -c "VACUUM ANALYZE;"
docker exec postgres psql -U postgres -d network_probe -c "REINDEX DATABASE network_probe;"

# 4. 清理旧的拨测结果（保留90天）
echo "[$DATE] Cleaning old task results..." >> $LOG_FILE
docker exec postgres psql -U postgres -d network_probe -c "
DELETE FROM task_results 
WHERE execution_time < NOW() - INTERVAL '90 days';"

# 5. 更新统计信息
echo "[$DATE] Updating statistics..." >> $LOG_FILE
docker exec postgres psql -U postgres -d network_probe -c "
UPDATE pg_stat_statements_reset();"

# 6. 检查磁盘空间
echo "[$DATE] Checking disk space..." >> $LOG_FILE
DISK_USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "[$DATE] WARNING: Disk usage is ${DISK_USAGE}%" >> $LOG_FILE
    # 发送告警
    curl -X POST "http://alertmanager:9093/api/v1/alerts" \
        -H "Content-Type: application/json" \
        -d '[{
            "labels": {
                "alertname": "DiskSpaceWarning",
                "severity": "warning",
                "instance": "'$(hostname)'"
            },
            "annotations": {
                "summary": "Disk space usage is '${DISK_USAGE}'%"
            }
        }]'
fi

# 7. 检查服务状态
echo "[$DATE] Checking service status..." >> $LOG_FILE
docker-compose ps | grep -v "Up" | grep -v "Name" && {
    echo "[$DATE] WARNING: Some services are not running" >> $LOG_FILE
    docker-compose ps >> $LOG_FILE
}

echo "[$DATE] Daily maintenance completed." >> $LOG_FILE
```

#### 周维护任务

```bash
#!/bin/bash
# scripts/weekly-maintenance.sh

LOG_FILE="/var/log/network-probe/maintenance.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting weekly maintenance..." >> $LOG_FILE

# 1. 完整数据库备份
echo "[$DATE] Creating database backup..." >> $LOG_FILE
/opt/network-probe/scripts/backup-database.sh

# 2. 配置文件备份
echo "[$DATE] Backing up configuration..." >> $LOG_FILE
/opt/network-probe/scripts/backup-config.sh

# 3. 系统更新检查
echo "[$DATE] Checking for system updates..." >> $LOG_FILE
apt list --upgradable 2>/dev/null | grep -v "WARNING" >> $LOG_FILE

# 4. 证书检查
echo "[$DATE] Checking SSL certificates..." >> $LOG_FILE
CERT_EXPIRY=$(openssl x509 -in /etc/ssl/certs/server.crt -noout -dates | grep "notAfter" | cut -d= -f2)
CERT_EXPIRY_EPOCH=$(date -d "$CERT_EXPIRY" +%s)
CURRENT_EPOCH=$(date +%s)
DAYS_UNTIL_EXPIRY=$(( (CERT_EXPIRY_EPOCH - CURRENT_EPOCH) / 86400 ))

if [ $DAYS_UNTIL_EXPIRY -lt 30 ]; then
    echo "[$DATE] WARNING: SSL certificate expires in $DAYS_UNTIL_EXPIRY days" >> $LOG_FILE
fi

# 5. 性能报告生成
echo "[$DATE] Generating performance report..." >> $LOG_FILE
/opt/network-probe/scripts/generate-performance-report.sh

echo "[$DATE] Weekly maintenance completed." >> $LOG_FILE
```

### 2. 容量规划

#### 存储容量监控

```python
# scripts/capacity-planning.py
import psutil
import psycopg2
import redis
import json
from datetime import datetime, timedelta

class CapacityMonitor:
    def __init__(self):
        self.db_conn = psycopg2.connect(
            host="postgres",
            database="network_probe",
            user="postgres",
            password="password"
        )
        self.redis_conn = redis.Redis(host="redis", port=6379, password="password")
    
    def check_database_growth(self):
        """检查数据库增长趋势"""
        cursor = self.db_conn.cursor()
        
        # 获取表大小
        cursor.execute("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
        """)
        
        tables = cursor.fetchall()
        
        # 预测增长
        cursor.execute("""
            SELECT 
                DATE_TRUNC('day', execution_time) as date,
                COUNT(*) as daily_records
            FROM task_results 
            WHERE execution_time >= NOW() - INTERVAL '30 days'
            GROUP BY DATE_TRUNC('day', execution_time)
            ORDER BY date;
        """)
        
        daily_growth = cursor.fetchall()
        
        if daily_growth:
            avg_daily_records = sum(row[1] for row in daily_growth) / len(daily_growth)
            # 假设每条记录平均1KB
            daily_growth_mb = avg_daily_records * 1024 / 1024 / 1024
            monthly_growth_gb = daily_growth_mb * 30
            
            print(f"Average daily records: {avg_daily_records:.0f}")
            print(f"Estimated monthly growth: {monthly_growth_gb:.2f} GB")
        
        return tables, daily_growth
    
    def check_disk_usage(self):
        """检查磁盘使用情况"""
        disk_usage = psutil.disk_usage('/')
        
        total_gb = disk_usage.total / (1024**3)
        used_gb = disk_usage.used / (1024**3)
        free_gb = disk_usage.free / (1024**3)
        usage_percent = (used_gb / total_gb) * 100
        
        print(f"Disk Usage:")
        print(f"  Total: {total_gb:.2f} GB")
        print(f"  Used: {used_gb:.2f} GB ({usage_percent:.1f}%)")
        print(f"  Free: {free_gb:.2f} GB")
        
        return {
            'total_gb': total_gb,
            'used_gb': used_gb,
            'free_gb': free_gb,
            'usage_percent': usage_percent
        }
    
    def generate_capacity_report(self):
        """生成容量规划报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'database': {},
            'disk': {},
            'recommendations': []
        }
        
        # 数据库分析
        tables, growth = self.check_database_growth()
        report['database']['tables'] = tables
        report['database']['growth_trend'] = growth
        
        # 磁盘分析
        disk_info = self.check_disk_usage()
        report['disk'] = disk_info
        
        # 生成建议
        if disk_info['usage_percent'] > 80:
            report['recommendations'].append({
                'type': 'disk_space',
                'priority': 'high',
                'message': 'Disk usage is above 80%, consider expanding storage'
            })
        
        if disk_info['usage_percent'] > 70:
            report['recommendations'].append({
                'type': 'data_cleanup',
                'priority': 'medium',
                'message': 'Consider implementing data archival strategy'
            })
        
        # 保存报告
        with open(f'/var/log/network-probe/capacity-report-{datetime.now().strftime("%Y%m%d")}.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        return report

if __name__ == "__main__":
    monitor = CapacityMonitor()
    report = monitor.generate_capacity_report()
    print("Capacity report generated successfully")
```

### 3. 安全维护

#### 安全检查脚本

```bash
#!/bin/bash
# scripts/security-check.sh

LOG_FILE="/var/log/network-probe/security-check.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting security check..." >> $LOG_FILE

# 1. 检查失败的登录尝试
echo "[$DATE] Checking failed login attempts..." >> $LOG_FILE
FAILED_LOGINS=$(grep "authentication failure" /var/log/auth.log | wc -l)
if [ $FAILED_LOGINS -gt 10 ]; then
    echo "[$DATE] WARNING: $FAILED_LOGINS failed login attempts detected" >> $LOG_FILE
fi

# 2. 检查开放端口
echo "[$DATE] Checking open ports..." >> $LOG_FILE
netstat -tuln | grep LISTEN >> $LOG_FILE

# 3. 检查SSL证书
echo "[$DATE] Checking SSL certificate..." >> $LOG_FILE
CERT_EXPIRY=$(openssl x509 -in /etc/ssl/certs/server.crt -noout -dates | grep "notAfter" | cut -d= -f2)
echo "[$DATE] Certificate expires: $CERT_EXPIRY" >> $LOG_FILE

# 4. 检查文件权限
echo "[$DATE] Checking file permissions..." >> $LOG_FILE
find /etc/network-probe -type f -perm /o+w -exec echo "World-writable file: {}" \; >> $LOG_FILE
find /opt/network-probe -type f -perm /o+w -exec echo "World-writable file: {}" \; >> $LOG_FILE

# 5. 检查系统更新
echo "[$DATE] Checking security updates..." >> $LOG_FILE
apt list --upgradable 2>/dev/null | grep -i security >> $LOG_FILE

# 6. 检查用户账户
echo "[$DATE] Checking user accounts..." >> $LOG_FILE
awk -F: '$3 >= 1000 && $3 < 65534 {print $1}' /etc/passwd >> $LOG_FILE

echo "[$DATE] Security check completed." >> $LOG_FILE
```

#### 漏洞扫描

```bash
#!/bin/bash
# scripts/vulnerability-scan.sh

# 使用Lynis进行系统安全审计
if command -v lynis &> /dev/null; then
    echo "Running Lynis security audit..."
    lynis audit system --quick --quiet
else
    echo "Installing Lynis..."
    apt update && apt install -y lynis
    lynis audit system --quick --quiet
fi

# Docker容器安全扫描
if command -v docker &> /dev/null; then
    echo "Scanning Docker images for vulnerabilities..."
    
    # 扫描管理平台镜像
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
        aquasec/trivy image network-probe/management:latest
    
    # 扫描代理镜像
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
        aquasec/trivy image network-probe/agent:latest
fi

# 网络端口扫描
if command -v nmap &> /dev/null; then
    echo "Scanning network ports..."
    nmap -sS -O localhost
fi
```

## 故障处理

### 1. 常见故障处理流程

#### 服务不可用处理

```bash
#!/bin/bash
# scripts/service-recovery.sh

SERVICE_NAME=$1
LOG_FILE="/var/log/network-probe/recovery.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

if [ -z "$SERVICE_NAME" ]; then
    echo "Usage: $0 <service_name>"
    exit 1
fi

echo "[$DATE] Starting recovery for service: $SERVICE_NAME" >> $LOG_FILE

case $SERVICE_NAME in
    "management")
        echo "[$DATE] Recovering management service..." >> $LOG_FILE
        
        # 检查容器状态
        if ! docker ps | grep -q management; then
            echo "[$DATE] Management container is not running, starting..." >> $LOG_FILE
            docker-compose up -d management
        fi
        
        # 检查数据库连接
        if ! docker exec management python -c "from management_platform.database.connection import test_connection; test_connection()"; then
            echo "[$DATE] Database connection failed, restarting postgres..." >> $LOG_FILE
            docker-compose restart postgres
            sleep 30
            docker-compose restart management
        fi
        ;;
        
    "postgres")
        echo "[$DATE] Recovering postgres service..." >> $LOG_FILE
        
        # 检查数据目录
        if [ ! -d "/var/lib/postgresql/data" ]; then
            echo "[$DATE] ERROR: PostgreSQL data directory missing" >> $LOG_FILE
            exit 1
        fi
        
        # 重启服务
        docker-compose restart postgres
        
        # 等待服务就绪
        timeout=60
        while [ $timeout -gt 0 ]; do
            if docker exec postgres pg_isready -U postgres; then
                echo "[$DATE] PostgreSQL is ready" >> $LOG_FILE
                break
            fi
            sleep 1
            ((timeout--))
        done
        
        if [ $timeout -eq 0 ]; then
            echo "[$DATE] ERROR: PostgreSQL failed to start within 60 seconds" >> $LOG_FILE
            exit 1
        fi
        ;;
        
    "redis")
        echo "[$DATE] Recovering redis service..." >> $LOG_FILE
        docker-compose restart redis
        ;;
        
    *)
        echo "[$DATE] Unknown service: $SERVICE_NAME" >> $LOG_FILE
        exit 1
        ;;
esac

echo "[$DATE] Recovery completed for service: $SERVICE_NAME" >> $LOG_FILE
```

#### 数据恢复流程

```bash
#!/bin/bash
# scripts/disaster-recovery.sh

BACKUP_FILE=$1
RECOVERY_TYPE=$2  # full, partial, point-in-time

if [ $# -lt 2 ]; then
    echo "Usage: $0 <backup_file> <recovery_type>"
    echo "Recovery types: full, partial, point-in-time"
    exit 1
fi

LOG_FILE="/var/log/network-probe/disaster-recovery.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting disaster recovery..." >> $LOG_FILE
echo "[$DATE] Backup file: $BACKUP_FILE" >> $LOG_FILE
echo "[$DATE] Recovery type: $RECOVERY_TYPE" >> $LOG_FILE

# 创建恢复前备份
echo "[$DATE] Creating pre-recovery backup..." >> $LOG_FILE
/opt/network-probe/scripts/backup-database.sh

case $RECOVERY_TYPE in
    "full")
        echo "[$DATE] Performing full recovery..." >> $LOG_FILE
        
        # 停止应用服务
        docker-compose stop management
        
        # 清空数据库
        docker exec postgres psql -U postgres -c "DROP DATABASE IF EXISTS network_probe;"
        docker exec postgres psql -U postgres -c "CREATE DATABASE network_probe;"
        
        # 恢复数据
        if [[ $BACKUP_FILE == *.gz ]]; then
            gunzip -c $BACKUP_FILE | docker exec -i postgres psql -U postgres -d network_probe
        else
            docker exec -i postgres psql -U postgres -d network_probe < $BACKUP_FILE
        fi
        
        # 重启服务
        docker-compose start management
        ;;
        
    "partial")
        echo "[$DATE] Performing partial recovery..." >> $LOG_FILE
        # 实现部分恢复逻辑
        ;;
        
    "point-in-time")
        echo "[$DATE] Performing point-in-time recovery..." >> $LOG_FILE
        # 实现时间点恢复逻辑
        ;;
esac

echo "[$DATE] Disaster recovery completed" >> $LOG_FILE
```

### 2. 故障排除手册

#### 常见问题诊断

```bash
#!/bin/bash
# scripts/diagnose.sh

echo "=== Network Probe Platform Diagnostic Tool ==="
echo

# 1. 系统资源检查
echo "1. System Resources:"
echo "   CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
echo "   Memory Usage: $(free | grep Mem | awk '{printf "%.1f%%", $3/$2 * 100.0}')"
echo "   Disk Usage: $(df -h / | awk 'NR==2{printf "%s", $5}')"
echo

# 2. 服务状态检查
echo "2. Service Status:"
docker-compose ps
echo

# 3. 网络连接检查
echo "3. Network Connectivity:"
echo "   Management API: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health)"
echo "   Web Interface: $(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)"
echo "   Database: $(docker exec postgres pg_isready -U postgres && echo "OK" || echo "FAIL")"
echo "   Redis: $(docker exec redis redis-cli ping 2>/dev/null || echo "FAIL")"
echo

# 4. 日志错误检查
echo "4. Recent Errors:"
echo "   Management errors (last 10):"
docker logs management 2>&1 | grep -i error | tail -10
echo
echo "   Database errors (last 5):"
docker logs postgres 2>&1 | grep -i error | tail -5
echo

# 5. 性能指标
echo "5. Performance Metrics:"
echo "   Active connections: $(docker exec postgres psql -U postgres -d network_probe -t -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';")"
echo "   Database size: $(docker exec postgres psql -U postgres -d network_probe -t -c "SELECT pg_size_pretty(pg_database_size('network_probe'));")"
echo "   Redis memory: $(docker exec redis redis-cli info memory | grep used_memory_human | cut -d: -f2)"
echo

echo "=== Diagnostic Complete ==="
```

这个监控和维护指南提供了完整的运维体系，帮助运维团队有效监控和维护网络拨测平台。