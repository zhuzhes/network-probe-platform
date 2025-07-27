# API参考文档

## 概述

网络拨测平台提供完整的RESTful API，支持所有Web界面功能。API使用JSON格式进行数据交换，采用JWT认证机制。

**基础URL：** `https://api.network-probe.com/api/v1`

## 认证

### JWT认证

所有API请求（除了登录和注册）都需要在请求头中包含JWT令牌：

```http
Authorization: Bearer <jwt_token>
```

### 获取访问令牌

```http
POST /auth/token
Content-Type: application/json

{
    "username": "your_username",
    "password": "your_password"
}
```

**响应：**
```json
{
    "success": true,
    "data": {
        "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
        "token_type": "bearer",
        "expires_in": 3600,
        "refresh_token": "def50200..."
    }
}
```

### 刷新令牌

```http
POST /auth/refresh
Content-Type: application/json

{
    "refresh_token": "def50200..."
}
```

## 用户管理

### 用户注册

```http
POST /users
Content-Type: application/json

{
    "username": "testuser",
    "email": "test@example.com",
    "password": "securepassword",
    "company_name": "Test Company"
}
```

**响应：**
```json
{
    "success": true,
    "data": {
        "id": "uuid",
        "username": "testuser",
        "email": "test@example.com",
        "company_name": "Test Company",
        "credits": 0.0,
        "created_at": "2024-01-01T00:00:00Z"
    }
}
```

### 获取用户信息

```http
GET /users/me
Authorization: Bearer <jwt_token>
```

### 更新用户信息

```http
PUT /users/me
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
    "email": "newemail@example.com",
    "company_name": "New Company Name"
}
```

### 账户充值

```http
POST /users/me/credits
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
    "amount": 100.0,
    "payment_method": "credit_card",
    "payment_reference": "payment_id_123"
}
```

## 任务管理

### 创建拨测任务

```http
POST /tasks
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
    "name": "网站可用性测试",
    "description": "监控主网站的可用性",
    "protocol": "http",
    "target": "example.com",
    "port": 80,
    "frequency": 300,
    "timeout": 30,
    "priority": 5,
    "parameters": {
        "method": "GET",
        "path": "/",
        "headers": {
            "User-Agent": "NetworkProbe/1.0"
        },
        "follow_redirects": true,
        "verify_ssl": true
    },
    "preferred_location": "beijing",
    "preferred_isp": "china-telecom"
}
```

**协议特定参数：**

**ICMP:**
```json
{
    "protocol": "icmp",
    "parameters": {
        "packet_size": 64,
        "packet_count": 4,
        "interval": 1
    }
}
```

**TCP:**
```json
{
    "protocol": "tcp",
    "port": 80,
    "parameters": {
        "connect_timeout": 10,
        "keep_alive": false
    }
}
```

**UDP:**
```json
{
    "protocol": "udp",
    "port": 53,
    "parameters": {
        "packet_size": 64,
        "response_timeout": 5
    }
}
```

**HTTP/HTTPS:**
```json
{
    "protocol": "https",
    "port": 443,
    "parameters": {
        "method": "POST",
        "path": "/api/health",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer token"
        },
        "body": "{\"check\": \"health\"}",
        "follow_redirects": true,
        "verify_ssl": true,
        "expected_status": [200, 201]
    }
}
```

### 获取任务列表

```http
GET /tasks?page=1&size=20&status=active&protocol=http
Authorization: Bearer <jwt_token>
```

**查询参数：**
- `page`: 页码（默认1）
- `size`: 每页数量（默认20，最大100）
- `status`: 任务状态筛选
- `protocol`: 协议类型筛选
- `search`: 任务名称搜索

**响应：**
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": "uuid",
                "name": "网站可用性测试",
                "protocol": "http",
                "target": "example.com",
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "next_run": "2024-01-01T00:05:00Z"
            }
        ],
        "total": 1,
        "page": 1,
        "size": 20,
        "pages": 1
    }
}
```

### 获取任务详情

```http
GET /tasks/{task_id}
Authorization: Bearer <jwt_token>
```

### 更新任务

```http
PUT /tasks/{task_id}
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
    "name": "更新的任务名称",
    "frequency": 600,
    "status": "paused"
}
```

### 删除任务

```http
DELETE /tasks/{task_id}
Authorization: Bearer <jwt_token>
```

## 拨测结果

### 获取拨测结果

```http
GET /results?task_id={task_id}&start_time=2024-01-01T00:00:00Z&end_time=2024-01-02T00:00:00Z&page=1&size=50
Authorization: Bearer <jwt_token>
```

**查询参数：**
- `task_id`: 任务ID（必需）
- `start_time`: 开始时间（ISO 8601格式）
- `end_time`: 结束时间（ISO 8601格式）
- `agent_id`: 代理ID筛选
- `status`: 结果状态筛选
- `page`: 页码
- `size`: 每页数量

**响应：**
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": "uuid",
                "task_id": "uuid",
                "agent_id": "uuid",
                "execution_time": "2024-01-01T00:00:00Z",
                "duration": 150.5,
                "status": "success",
                "metrics": {
                    "response_time": 150.5,
                    "status_code": 200,
                    "content_length": 1024,
                    "dns_time": 10.2,
                    "connect_time": 50.3,
                    "ssl_time": 30.1
                },
                "agent": {
                    "id": "uuid",
                    "name": "Beijing-Agent-01",
                    "location": {
                        "country": "China",
                        "city": "Beijing"
                    },
                    "isp": "China Telecom"
                }
            }
        ],
        "total": 100,
        "page": 1,
        "size": 50,
        "pages": 2
    }
}
```

### 获取统计数据

```http
GET /statistics?task_id={task_id}&period=1d&metric=response_time
Authorization: Bearer <jwt_token>
```

**查询参数：**
- `task_id`: 任务ID
- `period`: 统计周期（1h, 1d, 1w, 1m）
- `metric`: 指标类型（response_time, success_rate, availability）
- `group_by`: 分组方式（agent, location, isp）

**响应：**
```json
{
    "success": true,
    "data": {
        "period": "1d",
        "metric": "response_time",
        "data_points": [
            {
                "timestamp": "2024-01-01T00:00:00Z",
                "value": 150.5,
                "count": 288
            }
        ],
        "summary": {
            "avg": 150.5,
            "min": 100.2,
            "max": 300.8,
            "p95": 250.3,
            "p99": 280.1
        }
    }
}
```

### 导出数据

```http
GET /export?task_id={task_id}&format=csv&start_time=2024-01-01T00:00:00Z&end_time=2024-01-02T00:00:00Z
Authorization: Bearer <jwt_token>
```

**查询参数：**
- `format`: 导出格式（csv, json, xlsx）
- 其他参数同获取结果接口

## 代理管理

### 获取代理列表

```http
GET /agents?status=online&location=beijing
Authorization: Bearer <jwt_token>
```

**响应：**
```json
{
    "success": true,
    "data": {
        "items": [
            {
                "id": "uuid",
                "name": "Beijing-Agent-01",
                "ip_address": "192.168.1.100",
                "location": {
                    "country": "China",
                    "city": "Beijing",
                    "latitude": 39.9042,
                    "longitude": 116.4074
                },
                "isp": "China Telecom",
                "status": "online",
                "version": "1.0.0",
                "capabilities": ["icmp", "tcp", "udp", "http", "https"],
                "last_heartbeat": "2024-01-01T00:00:00Z",
                "performance_metrics": {
                    "availability": 99.5,
                    "avg_response_time": 150.2,
                    "success_rate": 98.8
                },
                "resources": {
                    "cpu_usage": 25.5,
                    "memory_usage": 45.2,
                    "disk_usage": 60.1,
                    "load_average": 1.2
                }
            }
        ],
        "total": 1
    }
}
```

### 获取代理详情

```http
GET /agents/{agent_id}
Authorization: Bearer <jwt_token>
```

### 获取代理资源历史

```http
GET /agents/{agent_id}/resources?start_time=2024-01-01T00:00:00Z&end_time=2024-01-02T00:00:00Z
Authorization: Bearer <jwt_token>
```

## 通知管理

### 获取通知设置

```http
GET /notifications/settings
Authorization: Bearer <jwt_token>
```

### 更新通知设置

```http
PUT /notifications/settings
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
    "email_notifications": {
        "task_failure": true,
        "low_credits": true,
        "system_maintenance": true
    },
    "notification_email": "alerts@example.com",
    "thresholds": {
        "low_credits": 10.0,
        "failure_rate": 0.1
    }
}
```

### 获取通知历史

```http
GET /notifications/history?page=1&size=20
Authorization: Bearer <jwt_token>
```

## 错误处理

### 错误响应格式

```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "错误描述",
        "details": {
            "field": "具体错误信息"
        }
    }
}
```

### 常见错误代码

| 错误代码 | HTTP状态码 | 描述 |
|---------|-----------|------|
| INVALID_CREDENTIALS | 401 | 认证失败 |
| TOKEN_EXPIRED | 401 | 令牌已过期 |
| INSUFFICIENT_PERMISSIONS | 403 | 权限不足 |
| RESOURCE_NOT_FOUND | 404 | 资源不存在 |
| INVALID_PARAMETER | 400 | 参数验证失败 |
| INSUFFICIENT_CREDITS | 402 | 点数不足 |
| RATE_LIMIT_EXCEEDED | 429 | 请求频率超限 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |

## 限流规则

- 认证接口：每分钟10次
- 任务管理：每分钟100次
- 结果查询：每分钟200次
- 其他接口：每分钟50次

超出限制时返回429状态码，响应头包含：
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1640995200
```

## SDK和示例

### Python SDK示例

```python
import requests
from datetime import datetime, timedelta

class NetworkProbeAPI:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.token = self._get_token(username, password)
    
    def _get_token(self, username, password):
        response = requests.post(f"{self.base_url}/auth/token", json={
            "username": username,
            "password": password
        })
        return response.json()["data"]["access_token"]
    
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}
    
    def create_task(self, task_data):
        response = requests.post(
            f"{self.base_url}/tasks",
            json=task_data,
            headers=self._headers()
        )
        return response.json()
    
    def get_results(self, task_id, hours=24):
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        params = {
            "task_id": task_id,
            "start_time": start_time.isoformat() + "Z",
            "end_time": end_time.isoformat() + "Z"
        }
        
        response = requests.get(
            f"{self.base_url}/results",
            params=params,
            headers=self._headers()
        )
        return response.json()

# 使用示例
api = NetworkProbeAPI("https://api.network-probe.com/api/v1", "username", "password")

# 创建HTTP拨测任务
task = api.create_task({
    "name": "网站监控",
    "protocol": "https",
    "target": "example.com",
    "frequency": 300,
    "timeout": 30
})

# 获取拨测结果
results = api.get_results(task["data"]["id"])
```

### JavaScript SDK示例

```javascript
class NetworkProbeAPI {
    constructor(baseUrl, username, password) {
        this.baseUrl = baseUrl;
        this.getToken(username, password);
    }
    
    async getToken(username, password) {
        const response = await fetch(`${this.baseUrl}/auth/token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await response.json();
        this.token = data.data.access_token;
    }
    
    headers() {
        return { 'Authorization': `Bearer ${this.token}` };
    }
    
    async createTask(taskData) {
        const response = await fetch(`${this.baseUrl}/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...this.headers()
            },
            body: JSON.stringify(taskData)
        });
        return await response.json();
    }
    
    async getResults(taskId, hours = 24) {
        const endTime = new Date();
        const startTime = new Date(endTime.getTime() - hours * 60 * 60 * 1000);
        
        const params = new URLSearchParams({
            task_id: taskId,
            start_time: startTime.toISOString(),
            end_time: endTime.toISOString()
        });
        
        const response = await fetch(`${this.baseUrl}/results?${params}`, {
            headers: this.headers()
        });
        return await response.json();
    }
}
```

## 版本历史

### v1.0.0
- 初始API版本
- 基础CRUD操作
- JWT认证

### v1.1.0
- 新增批量操作接口
- 增强统计数据API
- 支持数据导出

### v1.2.0
- 新增通知管理API
- 优化错误处理
- 增加限流机制