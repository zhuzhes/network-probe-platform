# 开发指南

## 概述

本文档为网络拨测平台的开发人员提供详细的开发指南，包括环境搭建、代码规范、开发流程、测试策略等内容。

## 开发环境搭建

### 系统要求

- Python 3.11+
- Node.js 16+
- Docker 20.10+
- Git 2.30+

### 本地开发环境

#### 1. 克隆项目

```bash
git clone https://github.com/company/network-probe-platform.git
cd network-probe-platform
```

#### 2. 后端环境搭建

```bash
# 创建Python虚拟环境
python -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 升级pip
pip install --upgrade pip

# 安装开发依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

#### 3. 前端环境搭建

```bash
cd management_platform/web
npm install
```

#### 4. 数据库环境

```bash
# 启动数据库服务
docker-compose up -d postgres redis rabbitmq

# 等待服务启动
sleep 10

# 运行数据库迁移
alembic upgrade head

# 创建测试数据
python scripts/init_db.py
```

#### 5. 配置文件

复制环境配置文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的环境变量：

```env
# 数据库配置
DATABASE_URL=postgresql://postgres:password@localhost:5432/network_probe
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# JWT配置
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# 邮件配置
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# 开发模式
DEBUG=true
LOG_LEVEL=DEBUG
```

### 开发服务启动

#### 后端服务

```bash
# 启动API服务
uvicorn management_platform.api.main:app --reload --host 0.0.0.0 --port 8000

# 启动任务调度器
python -m management_platform.scheduler.scheduler

# 启动通知服务
celery -A management_platform.notifications.queue worker --loglevel=info
```

#### 前端服务

```bash
cd management_platform/web
npm run dev
```

#### 代理服务（测试用）

```bash
python -m agent --config agent/config/dev.yaml
```

## 项目结构

```
network-probe-platform/
├── agent/                          # 代理节点代码
│   ├── core/                       # 核心功能
│   ├── protocols/                  # 协议插件
│   ├── monitoring/                 # 资源监控
│   └── updater/                    # OTA更新
├── management_platform/            # 管理平台代码
│   ├── api/                        # API服务
│   ├── database/                   # 数据访问层
│   ├── scheduler/                  # 任务调度
│   ├── notifications/              # 通知系统
│   ├── updater/                    # 更新管理
│   └── web/                        # 前端代码
├── shared/                         # 共享代码
│   ├── models/                     # 数据模型
│   ├── security/                   # 安全模块
│   └── utils/                      # 工具函数
├── tests/                          # 测试代码
│   ├── unit/                       # 单元测试
│   ├── integration/                # 集成测试
│   └── e2e/                        # 端到端测试
├── deployment/                     # 部署配置
├── docs/                           # 文档
└── scripts/                        # 脚本工具
```

## 代码规范

### Python代码规范

#### 1. 代码风格

遵循 PEP 8 规范，使用以下工具确保代码质量：

```bash
# 代码格式化
black .

# 导入排序
isort .

# 代码检查
flake8 .

# 类型检查
mypy .
```

#### 2. 命名规范

```python
# 变量和函数：snake_case
user_name = "john"
def get_user_info():
    pass

# 类名：PascalCase
class UserManager:
    pass

# 常量：UPPER_SNAKE_CASE
MAX_RETRY_COUNT = 3

# 私有成员：前缀下划线
class MyClass:
    def __init__(self):
        self._private_var = None
        self.__very_private = None
```

#### 3. 文档字符串

使用Google风格的文档字符串：

```python
def create_task(name: str, protocol: str, target: str) -> Task:
    """创建拨测任务。
    
    Args:
        name: 任务名称
        protocol: 协议类型 (icmp, tcp, udp, http, https)
        target: 目标地址
        
    Returns:
        创建的任务对象
        
    Raises:
        ValueError: 当参数无效时
        DatabaseError: 当数据库操作失败时
    """
    pass
```

#### 4. 类型注解

所有函数都应该包含类型注解：

```python
from typing import List, Optional, Dict, Any
from datetime import datetime

def process_results(
    results: List[TaskResult], 
    start_time: datetime,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    """处理拨测结果"""
    pass
```

### JavaScript/TypeScript代码规范

#### 1. 使用TypeScript

所有新的前端代码都应该使用TypeScript：

```typescript
// 接口定义
interface Task {
  id: string;
  name: string;
  protocol: 'icmp' | 'tcp' | 'udp' | 'http' | 'https';
  target: string;
  frequency: number;
  status: 'active' | 'paused' | 'completed';
}

// 函数类型注解
function createTask(taskData: Partial<Task>): Promise<Task> {
  return api.post('/tasks', taskData);
}
```

#### 2. Vue组件规范

```vue
<template>
  <div class="task-list">
    <el-table :data="tasks" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" />
      <el-table-column prop="name" label="任务名称" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import type { Task } from '@/types/task';

// 响应式数据
const tasks = ref<Task[]>([]);
const selectedTasks = ref<Task[]>([]);

// 生命周期
onMounted(async () => {
  await loadTasks();
});

// 方法
const loadTasks = async (): Promise<void> => {
  try {
    const response = await api.get('/tasks');
    tasks.value = response.data;
  } catch (error) {
    console.error('Failed to load tasks:', error);
  }
};

const handleSelectionChange = (selection: Task[]): void => {
  selectedTasks.value = selection;
};
</script>

<style scoped>
.task-list {
  padding: 20px;
}
</style>
```

## 开发流程

### Git工作流

采用Git Flow工作流：

```bash
# 创建功能分支
git checkout -b feature/task-management

# 开发完成后提交
git add .
git commit -m "feat: add task management API"

# 推送到远程
git push origin feature/task-management

# 创建Pull Request
# 代码审查通过后合并到develop分支
```

### 提交信息规范

使用Conventional Commits规范：

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

类型说明：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建或工具相关

示例：
```
feat(api): add task creation endpoint

- Add POST /api/v1/tasks endpoint
- Implement task validation
- Add unit tests

Closes #123
```

### 代码审查

所有代码都必须经过代码审查：

#### 审查清单

**功能性**：
- [ ] 功能是否按需求实现
- [ ] 边界条件是否处理
- [ ] 错误处理是否完善

**代码质量**：
- [ ] 代码是否清晰易读
- [ ] 是否遵循代码规范
- [ ] 是否有适当的注释

**性能**：
- [ ] 是否有性能问题
- [ ] 数据库查询是否优化
- [ ] 是否有内存泄漏

**安全性**：
- [ ] 输入验证是否充分
- [ ] 是否有安全漏洞
- [ ] 敏感信息是否保护

**测试**：
- [ ] 是否有足够的测试覆盖
- [ ] 测试是否通过
- [ ] 是否有集成测试

## 测试策略

### 测试金字塔

```
    /\
   /  \     E2E Tests (少量)
  /____\
 /      \   Integration Tests (适量)
/__________\ Unit Tests (大量)
```

### 单元测试

使用pytest进行单元测试：

```python
# tests/unit/test_task_service.py
import pytest
from unittest.mock import Mock, patch
from management_platform.services.task_service import TaskService
from shared.models.task import Task

class TestTaskService:
    def setup_method(self):
        self.mock_repo = Mock()
        self.service = TaskService(self.mock_repo)
    
    def test_create_task_success(self):
        # Arrange
        task_data = {
            'name': 'Test Task',
            'protocol': 'http',
            'target': 'example.com'
        }
        expected_task = Task(**task_data)
        self.mock_repo.create.return_value = expected_task
        
        # Act
        result = self.service.create_task(task_data)
        
        # Assert
        assert result == expected_task
        self.mock_repo.create.assert_called_once_with(task_data)
    
    def test_create_task_invalid_protocol(self):
        # Arrange
        task_data = {
            'name': 'Test Task',
            'protocol': 'invalid',
            'target': 'example.com'
        }
        
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid protocol"):
            self.service.create_task(task_data)
```

### 集成测试

测试组件间的交互：

```python
# tests/integration/test_task_api.py
import pytest
from fastapi.testclient import TestClient
from management_platform.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    # 获取认证token
    response = client.post("/api/v1/auth/token", json={
        "username": "testuser",
        "password": "testpass"
    })
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}

class TestTaskAPI:
    def test_create_task(self, client, auth_headers):
        # Arrange
        task_data = {
            "name": "Integration Test Task",
            "protocol": "http",
            "target": "httpbin.org",
            "frequency": 300
        }
        
        # Act
        response = client.post(
            "/api/v1/tasks",
            json=task_data,
            headers=auth_headers
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == task_data["name"]
```

### 端到端测试

使用Playwright进行前端E2E测试：

```python
# tests/e2e/test_task_workflow.py
import pytest
from playwright.sync_api import Page, expect

class TestTaskWorkflow:
    def test_create_and_run_task(self, page: Page):
        # 登录
        page.goto("http://localhost:3000/login")
        page.fill('[data-testid="username"]', "testuser")
        page.fill('[data-testid="password"]', "testpass")
        page.click('[data-testid="login-button"]')
        
        # 创建任务
        page.goto("http://localhost:3000/tasks")
        page.click('[data-testid="create-task-button"]')
        
        page.fill('[data-testid="task-name"]', "E2E Test Task")
        page.select_option('[data-testid="protocol"]', "http")
        page.fill('[data-testid="target"]', "httpbin.org")
        page.fill('[data-testid="frequency"]', "300")
        
        page.click('[data-testid="save-task-button"]')
        
        # 验证任务创建成功
        expect(page.locator('[data-testid="success-message"]')).to_be_visible()
        expect(page.locator('text=E2E Test Task')).to_be_visible()
```

### 测试配置

```python
# pytest.ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --strict-markers
    --disable-warnings
    --cov=.
    --cov-report=html
    --cov-report=term-missing
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow running tests
```

## 数据库开发

### 数据库迁移

使用Alembic进行数据库版本管理：

```bash
# 创建迁移文件
alembic revision --autogenerate -m "Add task table"

# 应用迁移
alembic upgrade head

# 回滚迁移
alembic downgrade -1
```

### 模型定义

```python
# shared/models/task.py
from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from shared.models.base import BaseModel

class Task(BaseModel):
    __tablename__ = 'tasks'
    
    name = Column(String(255), nullable=False, index=True)
    protocol = Column(String(50), nullable=False)
    target = Column(String(255), nullable=False)
    port = Column(Integer)
    frequency = Column(Integer, nullable=False)
    timeout = Column(Integer, default=30)
    parameters = Column(JSON)
    status = Column(String(50), default='active', index=True)
    
    # 外键关系
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    user = relationship("User", back_populates="tasks")
    
    # 反向关系
    results = relationship("TaskResult", back_populates="task", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, name={self.name}, protocol={self.protocol})>"
```

### 仓库模式

```python
# management_platform/database/repositories.py
from typing import List, Optional
from sqlalchemy.orm import Session
from shared.models.task import Task

class TaskRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, task_data: dict) -> Task:
        task = Task(**task_data)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
    
    def get_by_id(self, task_id: str) -> Optional[Task]:
        return self.db.query(Task).filter(Task.id == task_id).first()
    
    def get_by_user(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Task]:
        return (self.db.query(Task)
                .filter(Task.user_id == user_id)
                .offset(skip)
                .limit(limit)
                .all())
    
    def update(self, task_id: str, update_data: dict) -> Optional[Task]:
        task = self.get_by_id(task_id)
        if task:
            for key, value in update_data.items():
                setattr(task, key, value)
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def delete(self, task_id: str) -> bool:
        task = self.get_by_id(task_id)
        if task:
            self.db.delete(task)
            self.db.commit()
            return True
        return False
```

## API开发

### API设计原则

1. **RESTful设计**：使用标准HTTP方法和状态码
2. **版本控制**：URL中包含版本号 `/api/v1/`
3. **统一响应格式**：成功和错误都使用统一格式
4. **分页支持**：列表接口支持分页
5. **过滤和排序**：支持查询参数过滤

### API实现示例

```python
# management_platform/api/routes/tasks.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from management_platform.api.dependencies import get_current_user, get_db
from management_platform.database.repositories import TaskRepository
from shared.models.user import User
from shared.schemas.task import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建拨测任务"""
    try:
        repo = TaskRepository(db)
        task = repo.create({
            **task_data.dict(),
            "user_id": current_user.id
        })
        return TaskResponse(success=True, data=task)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取任务列表"""
    repo = TaskRepository(db)
    tasks = repo.get_by_user(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        filters={"status": status, "protocol": protocol}
    )
    return [TaskResponse(success=True, data=task) for task in tasks]
```

### 数据验证

使用Pydantic进行数据验证：

```python
# shared/schemas/task.py
from pydantic import BaseModel, validator
from typing import Optional, Dict, Any
from datetime import datetime

class TaskBase(BaseModel):
    name: str
    protocol: str
    target: str
    port: Optional[int] = None
    frequency: int
    timeout: int = 30
    parameters: Optional[Dict[str, Any]] = None

class TaskCreate(TaskBase):
    @validator('protocol')
    def validate_protocol(cls, v):
        allowed_protocols = ['icmp', 'tcp', 'udp', 'http', 'https']
        if v not in allowed_protocols:
            raise ValueError(f'Protocol must be one of {allowed_protocols}')
        return v
    
    @validator('frequency')
    def validate_frequency(cls, v):
        if v < 60:
            raise ValueError('Frequency must be at least 60 seconds')
        return v

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    frequency: Optional[int] = None
    timeout: Optional[int] = None
    status: Optional[str] = None

class TaskResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    
    class Config:
        from_attributes = True
```

## 前端开发

### 组件开发

```vue
<!-- src/components/TaskForm.vue -->
<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-width="120px"
    @submit.prevent="handleSubmit"
  >
    <el-form-item label="任务名称" prop="name">
      <el-input v-model="form.name" placeholder="请输入任务名称" />
    </el-form-item>
    
    <el-form-item label="协议类型" prop="protocol">
      <el-select v-model="form.protocol" placeholder="请选择协议">
        <el-option
          v-for="protocol in protocols"
          :key="protocol.value"
          :label="protocol.label"
          :value="protocol.value"
        />
      </el-select>
    </el-form-item>
    
    <el-form-item label="目标地址" prop="target">
      <el-input v-model="form.target" placeholder="请输入目标地址" />
    </el-form-item>
    
    <el-form-item>
      <el-button type="primary" @click="handleSubmit">
        {{ isEdit ? '更新' : '创建' }}
      </el-button>
      <el-button @click="handleCancel">取消</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import type { FormInstance, FormRules } from 'element-plus';
import { createTask, updateTask } from '@/api/tasks';
import type { Task, TaskCreateRequest } from '@/types/task';

interface Props {
  task?: Task;
  isEdit?: boolean;
}

interface Emits {
  (e: 'success', task: Task): void;
  (e: 'cancel'): void;
}

const props = withDefaults(defineProps<Props>(), {
  isEdit: false
});

const emit = defineEmits<Emits>();

const formRef = ref<FormInstance>();

const form = reactive<TaskCreateRequest>({
  name: props.task?.name || '',
  protocol: props.task?.protocol || 'http',
  target: props.task?.target || '',
  frequency: props.task?.frequency || 300,
  timeout: props.task?.timeout || 30
});

const protocols = [
  { label: 'ICMP (Ping)', value: 'icmp' },
  { label: 'TCP', value: 'tcp' },
  { label: 'UDP', value: 'udp' },
  { label: 'HTTP', value: 'http' },
  { label: 'HTTPS', value: 'https' }
];

const rules: FormRules = {
  name: [
    { required: true, message: '请输入任务名称', trigger: 'blur' },
    { min: 1, max: 255, message: '长度在 1 到 255 个字符', trigger: 'blur' }
  ],
  protocol: [
    { required: true, message: '请选择协议类型', trigger: 'change' }
  ],
  target: [
    { required: true, message: '请输入目标地址', trigger: 'blur' }
  ]
};

const handleSubmit = async (): Promise<void> => {
  if (!formRef.value) return;
  
  try {
    await formRef.value.validate();
    
    const task = props.isEdit && props.task
      ? await updateTask(props.task.id, form)
      : await createTask(form);
    
    emit('success', task);
  } catch (error) {
    console.error('Form validation failed:', error);
  }
};

const handleCancel = (): void => {
  emit('cancel');
};
</script>
```

### 状态管理

使用Pinia进行状态管理：

```typescript
// src/stores/tasks.ts
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Task } from '@/types/task';
import * as taskApi from '@/api/tasks';

export const useTaskStore = defineStore('tasks', () => {
  // State
  const tasks = ref<Task[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // Getters
  const activeTasks = computed(() => 
    tasks.value.filter(task => task.status === 'active')
  );

  const taskCount = computed(() => tasks.value.length);

  // Actions
  const fetchTasks = async (): Promise<void> => {
    loading.value = true;
    error.value = null;
    
    try {
      const response = await taskApi.getTasks();
      tasks.value = response.data;
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Unknown error';
    } finally {
      loading.value = false;
    }
  };

  const createTask = async (taskData: TaskCreateRequest): Promise<Task> => {
    const task = await taskApi.createTask(taskData);
    tasks.value.push(task);
    return task;
  };

  const updateTask = async (id: string, taskData: TaskUpdateRequest): Promise<Task> => {
    const updatedTask = await taskApi.updateTask(id, taskData);
    const index = tasks.value.findIndex(task => task.id === id);
    if (index !== -1) {
      tasks.value[index] = updatedTask;
    }
    return updatedTask;
  };

  const deleteTask = async (id: string): Promise<void> => {
    await taskApi.deleteTask(id);
    const index = tasks.value.findIndex(task => task.id === id);
    if (index !== -1) {
      tasks.value.splice(index, 1);
    }
  };

  return {
    // State
    tasks,
    loading,
    error,
    // Getters
    activeTasks,
    taskCount,
    // Actions
    fetchTasks,
    createTask,
    updateTask,
    deleteTask
  };
});
```

## 调试和故障排除

### 日志配置

```python
# shared/utils/logger.py
import logging
import structlog
from pythonjsonlogger import jsonlogger

def configure_logging():
    # 配置结构化日志
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# 使用示例
logger = structlog.get_logger(__name__)

logger.info(
    "task_created",
    task_id=task.id,
    user_id=user.id,
    protocol=task.protocol,
    target=task.target
)
```

### 性能分析

```python
# 使用装饰器进行性能监控
import time
import functools
from typing import Callable, Any

def monitor_performance(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(
                "function_executed",
                function=func.__name__,
                duration=duration,
                status="success"
            )
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "function_failed",
                function=func.__name__,
                duration=duration,
                error=str(e),
                status="error"
            )
            raise
    return wrapper

# 使用示例
@monitor_performance
async def create_task(task_data: dict) -> Task:
    # 任务创建逻辑
    pass
```

### 常见问题解决

#### 1. 数据库连接问题

```python
# 检查数据库连接
from sqlalchemy import text
from management_platform.database.connection import get_db

def check_database_connection():
    try:
        db = next(get_db())
        result = db.execute(text("SELECT 1"))
        print("Database connection successful")
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False
```

#### 2. WebSocket连接调试

```python
# 启用WebSocket调试日志
import websockets
import logging

logging.getLogger('websockets').setLevel(logging.DEBUG)

# 连接测试
async def test_websocket_connection():
    try:
        async with websockets.connect("ws://localhost:8000/ws") as websocket:
            await websocket.send("ping")
            response = await websocket.recv()
            print(f"Received: {response}")
    except Exception as e:
        print(f"WebSocket connection failed: {e}")
```

## 部署和发布

### 本地构建

```bash
# 构建Docker镜像
docker build -t network-probe/management:latest .
docker build -f Dockerfile.agent -t network-probe/agent:latest .

# 运行容器
docker run -d --name management -p 8000:8000 network-probe/management:latest
docker run -d --name agent network-probe/agent:latest
```

### CI/CD配置

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: |
        pytest tests/ --cov=. --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Build and push Docker images
      run: |
        docker build -t network-probe/management:${{ github.sha }} .
        docker build -f Dockerfile.agent -t network-probe/agent:${{ github.sha }} .
        # Push to registry
```

这个开发指南为团队提供了完整的开发流程和最佳实践，确保代码质量和开发效率。