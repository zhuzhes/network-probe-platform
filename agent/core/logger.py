"""代理日志系统"""

import os
import sys
import logging
import logging.handlers
from typing import Optional
from pathlib import Path


def setup_logger(
    name: str = "agent",
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True
) -> logging.Logger:
    """
    设置代理日志系统
    
    Args:
        name: 日志器名称
        level: 日志级别
        log_file: 日志文件路径，默认为 ~/.agent/logs/agent.log
        max_bytes: 单个日志文件最大字节数
        backup_count: 备份文件数量
        console_output: 是否输出到控制台
        
    Returns:
        配置好的日志器
    """
    logger = logging.getLogger(name)
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # 创建格式化器
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file is None:
        home_dir = Path.home()
        log_dir = home_dir / ".agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = str(log_dir / "agent.log")
    
    try:
        # 确保日志目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # 使用RotatingFileHandler实现日志轮转
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"日志系统已初始化，日志文件: {log_file}")
        
    except Exception as e:
        logger.error(f"无法创建日志文件处理器: {e}")
        # 如果文件处理器创建失败，至少保证控制台输出可用
        if not console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
    
    return logger


class AgentLogger:
    """代理日志管理器"""
    
    def __init__(self, name: str = "agent", **kwargs):
        """
        初始化日志管理器
        
        Args:
            name: 日志器名称
            **kwargs: 传递给setup_logger的其他参数
        """
        self.logger = setup_logger(name, **kwargs)
        self.name = name
    
    def debug(self, message: str, *args, **kwargs):
        """记录调试信息"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """记录信息"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """记录警告"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """记录错误"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """记录严重错误"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs):
        """记录异常信息"""
        self.logger.exception(message, *args, **kwargs)
    
    def set_level(self, level: str):
        """设置日志级别"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.setLevel(log_level)
        for handler in self.logger.handlers:
            handler.setLevel(log_level)
    
    def add_context(self, **context):
        """添加上下文信息到日志"""
        # 创建一个带上下文的适配器
        return logging.LoggerAdapter(self.logger, context)


# 默认日志器实例
default_logger = AgentLogger()