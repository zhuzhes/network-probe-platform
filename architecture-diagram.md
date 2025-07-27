# 网络拨测平台系统架构图

## 整体架构概览

```mermaid
graph TB
    %% 用户层
    subgraph "用户层 (User Layer)"
        A[Web浏览器]
        B[移动应用]
        C[第三方API]
    end
    
    %% 接入层
    subgraph "接入层 (Gateway Layer)"
        D[Nginx负载均衡]
        E[API网关]
    end
    
    %% 管理平台
    subgraph "管理平台 (Management Platform)"
        F[用户服务<br/>User Service]
        G[任务服务<br/>Task Service]
        H[代理服务<br/>Agent Service]
        I[通知服务<br/>Notification Service]
        J[分析服务<br/>Analytics Service]
        K[WebSocket服务<br/>WebSocket Service]
    end
    
    %% 调度层
    subgraph "调度层 (Scheduling Layer)"
        L[任务调度器<br/>Task Scheduler]
        M[消息队列<br/>RabbitMQ]
        N[任务分配器<br/>Task Allocator]
    end
    
    %% 数据层
    subgraph "数据层 (Data Layer)"
        O[PostgreSQL<br/>主数据库]
        P[Redis<br/>缓存/会话]
        Q[时序数据库<br/>InfluxDB]
    end
    
    %% 代理网络
    subgraph "代理网络 (Agent Network)"
        R[代理节点1<br/>Agent Node 1]
        S[代理节点2<br/>Agent Node 2]
        T[代理节点N<br/>Agent Node N]
    end
    
    %% 监控系统
    subgraph "监控系统 (Monitoring)"
        U[Prometheus]
        V[Grafana]
        W[ELK Stack]
    end
    
    %% 连接关系
    A --> D
    B --> D
    C --> D
    D --> E
    E --> F
    E --> G
    E --> H
    E --> I
    E --> J
    E --> K
    
    F --> O
    G --> O
    H --> O
    I --> P
    J --> Q
    K --> M
    
    G --> L
    L --> M
    M --> N
    N --> R
    N --> S
    N --> T
    
    R --> M
    S --> M
    T --> M
    
    %% 监控连接
    F -.-> U
    G -.-> U
    H -.-> U
    R -.-> U
    S -.-> U
    T -.-> U
    U --> V
    F -.-> W
    G -.-> W
    H -.-> W
```

## 代理节点内部架构

```mermaid
graph TB
    subgraph "代理节点 (Agent Node)"
        A1[代理核心<br/>Agent Core]
        
        subgraph "通信模块"
            B1[WebSocket客户端<br/>WebSocket Client]
            B2[消息处理器<br/>Message Handler]
        end
        
        subgraph "任务执行模块"
            C1[任务执行器<br/>Task Executor]
            C2[结果收集器<br/>Result Collector]
        end
        
        subgraph "协议插件"
            D1[ICMP插件<br/>ICMP Plugin]
            D2[TCP插件<br/>TCP Plugin]
            D3[UDP插件<br/>UDP Plugin]
            D4[HTTP插件<br/>HTTP Plugin]
        end
        
        subgraph "监控模块"
            E1[资源监控器<br/>Resource Monitor]
            E2[性能统计<br/>Performance Stats]
        end
        
        subgraph "更新模块"
            F1[更新客户端<br/>Update Client]
            F2[版本管理器<br/>Version Manager]
        end
    end
    
    A1 --> B1
    A1 --> C1
    A1 --> E1
    A1 --> F1
    
    B1 --> B2
    C1 --> C2
    C1 --> D1
    C1 --> D2
    C1 --> D3
    C1 --> D4
    
    E1 --> E2
    F1 --> F2
    
    B2 --> C1
    C2 --> B1
    E2 --> B1
```

## 数据流架构

```mermaid
sequenceDiagram
    participant U as 用户
    participant W as Web界面
    participant A as API网关
    participant T as 任务服务
    participant S as 调度器
    participant Q as 消息队列
    participant AG as 代理节点
    participant D as 数据库
    
    U->>W: 创建拨测任务
    W->>A: POST /api/tasks
    A->>T: 创建任务请求
    T->>D: 保存任务信息
    T->>S: 提交任务到调度器
    S->>Q: 发送任务到队列
    Q->>AG: 分发任务到代理
    AG->>AG: 执行拨测任务
    AG->>Q: 返回执行结果
    Q->>T: 收集任务结果
    T->>D: 保存结果数据
    T->>W: 推送结果更新
    W->>U: 显示拨测结果
```

## 技术栈架构

```mermaid
graph LR
    subgraph "前端技术栈"
        A1[Vue.js 3]
        A2[TypeScript]
        A3[Element Plus]
        A4[ECharts]
        A5[Axios]
    end
    
    subgraph "后端技术栈"
        B1[Python 3.11+]
        B2[FastAPI]
        B3[SQLAlchemy]
        B4[Pydantic]
        B5[AsyncIO]
    end
    
    subgraph "数据存储"
        C1[PostgreSQL]
        C2[Redis]
        C3[InfluxDB]
    end
    
    subgraph "消息队列"
        D1[RabbitMQ]
        D2[Celery]
    end
    
    subgraph "基础设施"
        E1[Docker]
        E2[Kubernetes]
        E3[Nginx]
        E4[Prometheus]
        E5[Grafana]
    end
    
    A1 --> B2
    B2 --> C1
    B2 --> C2
    B2 --> D1
    B5 --> D2
    
    E1 --> E2
    E3 --> B2
    E4 --> E5
```

## 部署架构

```mermaid
graph TB
    subgraph "生产环境 (Production)"
        subgraph "Kubernetes集群"
            subgraph "管理平台Pod"
                P1[API服务 x3]
                P2[调度服务 x2]
                P3[通知服务 x2]
            end
            
            subgraph "数据服务"
                D1[PostgreSQL主从]
                D2[Redis集群]
                D3[RabbitMQ集群]
            end
            
            subgraph "监控服务"
                M1[Prometheus]
                M2[Grafana]
                M3[ELK Stack]
            end
        end
        
        subgraph "代理网络"
            A1[代理节点 - 北京]
            A2[代理节点 - 上海]
            A3[代理节点 - 广州]
            A4[代理节点 - 海外]
        end
        
        subgraph "负载均衡"
            L1[云负载均衡器]
            L2[Nginx Ingress]
        end
    end
    
    L1 --> L2
    L2 --> P1
    P1 --> D1
    P1 --> D2
    P2 --> D3
    
    P2 --> A1
    P2 --> A2
    P2 --> A3
    P2 --> A4
    
    P1 -.-> M1
    A1 -.-> M1
    A2 -.-> M1
    A3 -.-> M1
    A4 -.-> M1
```

## 安全架构

```mermaid
graph TB
    subgraph "安全层次"
        subgraph "网络安全"
            N1[防火墙]
            N2[VPN]
            N3[DDoS防护]
        end
        
        subgraph "应用安全"
            A1[JWT认证]
            A2[RBAC权限]
            A3[API限流]
            A4[CORS防护]
        end
        
        subgraph "数据安全"
            D1[TLS 1.3加密]
            D2[数据库加密]
            D3[敏感数据脱敏]
        end
        
        subgraph "代理安全"
            AG1[证书认证]
            AG2[双向TLS]
            AG3[最小权限]
        end
    end
    
    N1 --> A1
    A1 --> D1
    D1 --> AG1
    
    N2 --> A2
    A2 --> D2
    D2 --> AG2
    
    N3 --> A3
    A3 --> D3
    D3 --> AG3
    
    A4 --> A1
```

## 关键特性说明

### 1. 分布式架构
- **微服务设计**：各功能模块独立部署和扩展
- **水平扩展**：支持根据负载动态扩容
- **故障隔离**：单个服务故障不影响整体系统

### 2. 高可用性
- **多实例部署**：关键服务多副本运行
- **负载均衡**：请求分发到多个实例
- **故障转移**：自动检测和恢复故障节点

### 3. 安全性
- **端到端加密**：所有通信使用TLS加密
- **身份认证**：JWT + RBAC权限控制
- **代理安全**：证书认证，不对外开放端口

### 4. 可扩展性
- **插件系统**：支持自定义协议插件
- **配置驱动**：通过配置文件灵活调整
- **API版本化**：向后兼容的API设计

### 5. 监控运维
- **全链路监控**：从用户请求到代理执行的完整监控
- **实时告警**：异常情况及时通知
- **日志聚合**：集中收集和分析日志

这个架构设计确保了系统的高性能、高可用性和可扩展性，能够支撑大规模的网络拨测需求。