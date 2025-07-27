"""API异常处理"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from pydantic import ValidationError
import structlog

logger = structlog.get_logger()


def setup_exception_handlers(app: FastAPI):
    """设置异常处理器"""
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """HTTP异常处理器"""
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.warning(
            "http_exception",
            request_id=request_id,
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP Error",
                "message": exc.detail,
                "status_code": exc.status_code,
                "request_id": request_id
            }
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Starlette HTTP异常处理器"""
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.warning(
            "starlette_http_exception",
            request_id=request_id,
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP Error",
                "message": exc.detail,
                "status_code": exc.status_code,
                "request_id": request_id
            }
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """请求验证异常处理器"""
        request_id = getattr(request.state, "request_id", "unknown")
        
        # 格式化验证错误
        errors = []
        for error in exc.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            message = error["msg"]
            errors.append(f"{field}: {message}")
        
        logger.warning(
            "validation_error",
            request_id=request_id,
            errors=errors,
            path=request.url.path
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation Error",
                "message": "Request validation failed",
                "details": errors,
                "request_id": request_id
            }
        )
    
    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        """Pydantic验证异常处理器"""
        request_id = getattr(request.state, "request_id", "unknown")
        
        # 格式化验证错误
        errors = []
        for error in exc.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            message = error["msg"]
            errors.append(f"{field}: {message}")
        
        logger.warning(
            "pydantic_validation_error",
            request_id=request_id,
            errors=errors,
            path=request.url.path
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation Error",
                "message": "Data validation failed",
                "details": errors,
                "request_id": request_id
            }
        )
    
    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(request: Request, exc: SQLAlchemyError):
        """数据库异常处理器"""
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.error(
            "database_error",
            request_id=request_id,
            error=str(exc),
            path=request.url.path
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Database Error",
                "message": "A database error occurred",
                "request_id": request_id
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """通用异常处理器"""
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.error(
            "unexpected_error",
            request_id=request_id,
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred",
                "request_id": request_id
            }
        )


class APIException(Exception):
    """自定义API异常基类"""
    
    def __init__(self, message: str, status_code: int = 400, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(APIException):
    """认证错误"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class AuthorizationError(APIException):
    """授权错误"""
    
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, status_code=403)


class NotFoundError(APIException):
    """资源未找到错误"""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class ConflictError(APIException):
    """冲突错误"""
    
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, status_code=409)


class ValidationError(APIException):
    """验证错误"""
    
    def __init__(self, message: str = "Validation failed", details: dict = None):
        super().__init__(message, status_code=422, details=details)


class RateLimitError(APIException):
    """限流错误"""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, status_code=429)


class InsufficientCreditsError(APIException):
    """点数不足错误"""
    
    def __init__(self, message: str = "Insufficient credits"):
        super().__init__(message, status_code=402)