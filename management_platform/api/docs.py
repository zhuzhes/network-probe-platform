"""API文档配置"""

from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI


def custom_openapi(app: FastAPI):
    """自定义OpenAPI文档"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="网络拨测平台API",
        version="1.0.0",
        description="""
        ## 网络拨测平台管理API
        
        这是一个用于管理网络拨测任务、代理和数据分析的RESTful API。
        
        ### 认证方式
        
        支持两种认证方式：
        
        1. **JWT Token**: 用于Web界面和临时访问
           - 在请求头中添加: `Authorization: Bearer <jwt_token>`
           - Token有效期: 30分钟
        
        2. **API Key**: 用于程序化访问
           - 在请求头中添加: `Authorization: Bearer <api_key>`
           - API Key格式: `npk_<random_string>`
        
        ### 权限系统
        
        - **管理员**: 拥有所有权限
        - **企业用户**: 只能访问自己的数据和资源
        
        ### 限流
        
        - 每个IP地址: 100次请求/分钟
        - 认证用户: 1000次请求/分钟
        
        ### 错误处理
        
        所有错误响应都包含以下字段：
        - `error`: 错误类型
        - `message`: 错误描述
        - `request_id`: 请求ID（用于问题追踪）
        
        ### 分页
        
        列表接口支持分页参数：
        - `page`: 页码（从1开始）
        - `size`: 每页大小（最大100）
        
        ### 排序
        
        列表接口支持排序参数：
        - `sort_by`: 排序字段
        - `sort_order`: 排序方向（asc/desc）
        """,
        routes=app.routes,
        tags=[
            {
                "name": "系统",
                "description": "系统状态和健康检查"
            },
            {
                "name": "认证",
                "description": "用户认证和授权"
            },
            {
                "name": "用户",
                "description": "用户管理和账户操作"
            },
            {
                "name": "任务",
                "description": "拨测任务管理"
            },
            {
                "name": "代理",
                "description": "代理管理和监控"
            },
            {
                "name": "数据分析",
                "description": "数据统计和分析"
            }
        ]
    )
    
    # 添加安全定义
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    
    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT Token或API Key认证"
    }
    
    # 为所有路径添加安全要求
    for path in openapi_schema["paths"]:
        for method in openapi_schema["paths"][path]:
            if method != "options":
                openapi_schema["paths"][path][method]["security"] = [
                    {"BearerAuth": []}
                ]
    
    # 移除不需要认证的路径的安全要求
    exempt_paths = ["/", "/health", "/docs", "/redoc", "/openapi.json"]
    for path in exempt_paths:
        if path in openapi_schema["paths"]:
            for method in openapi_schema["paths"][path]:
                if "security" in openapi_schema["paths"][path][method]:
                    del openapi_schema["paths"][path][method]["security"]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


def setup_docs(app: FastAPI):
    """设置API文档"""
    app.openapi = lambda: custom_openapi(app)