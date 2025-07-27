"""API服务器启动脚本"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import uvicorn
from shared.config import app_config


def main():
    """启动API服务器"""
    uvicorn.run(
        "management_platform.api.main:app",
        host=app_config.host,
        port=app_config.port,
        reload=app_config.debug,
        log_level="debug" if app_config.debug else "info",
        access_log=True,
    )


if __name__ == "__main__":
    main()