# 网络拨测平台 Web 界面

基于 Vue 3 + Element Plus 的现代化 Web 界面。

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **Vue Router** - 官方路由管理器
- **Pinia** - 状态管理
- **Element Plus** - Vue 3 组件库
- **Axios** - HTTP 客户端
- **Vite** - 构建工具
- **ECharts** - 数据可视化

## 项目结构

```
src/
├── components/          # 公共组件
│   └── Layout.vue      # 主布局组件
├── router/             # 路由配置
│   └── index.js
├── stores/             # Pinia 状态管理
│   ├── auth.js         # 认证状态
│   └── tasks.js        # 任务状态
├── utils/              # 工具函数
│   └── api.js          # API 请求封装
├── views/              # 页面组件
│   ├── Login.vue       # 登录页面
│   ├── Dashboard.vue   # 仪表板
│   ├── Tasks.vue       # 任务管理
│   ├── Agents.vue      # 代理管理
│   ├── Analytics.vue   # 数据分析
│   └── Profile.vue     # 个人资料
├── App.vue             # 根组件
└── main.js             # 入口文件
```

## 开发指南

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

### 构建生产版本

```bash
npm run build
```

### 代码检查

```bash
npm run lint
```

### 运行测试

```bash
npm run test
```

## 功能特性

### 已实现功能

- ✅ 用户认证系统（登录/注册）
- ✅ 响应式布局设计
- ✅ 路由守卫和权限控制
- ✅ API 请求封装和错误处理
- ✅ 基础仪表板界面

### 待实现功能

- ⏳ 任务管理界面（任务 12.2）
- ⏳ 代理管理界面（任务 12.3）
- ⏳ 数据可视化（任务 12.4）
- ⏳ 用户账户管理界面（任务 12.5）

## API 集成

Web 界面通过 `/api/v1` 前缀与后端 API 进行通信。主要接口包括：

- **认证接口**: `/auth/token`
- **用户接口**: `/users`
- **任务接口**: `/tasks`
- **代理接口**: `/agents`
- **分析接口**: `/analytics`

## 部署说明

### 开发环境

开发环境下，Vite 开发服务器会自动代理 API 请求到后端服务器（默认 `http://localhost:8000`）。

### 生产环境

生产环境下，需要配置 Web 服务器（如 Nginx）来：

1. 服务静态文件
2. 代理 API 请求到后端服务器
3. 处理 SPA 路由（History 模式）

示例 Nginx 配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /path/to/dist;
    index index.html;

    # 处理 SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 代理 API 请求
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 贡献指南

1. 遵循 Vue 3 Composition API 风格
2. 使用 Element Plus 组件库
3. 保持代码风格一致
4. 添加适当的注释和文档
5. 确保响应式设计兼容性