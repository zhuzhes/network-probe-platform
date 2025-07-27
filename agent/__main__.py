"""代理命令行入口"""

import asyncio
import argparse
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.core.agent import Agent
from agent.core.logger import setup_logger


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="网络拨测代理")
    
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="配置文件路径"
    )
    
    parser.add_argument(
        "--log-level",
        "-l",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="日志级别"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        help="日志文件路径"
    )
    
    parser.add_argument(
        "--no-console",
        action="store_true",
        help="不输出到控制台"
    )
    
    return parser.parse_args()


async def main():
    """主函数"""
    args = parse_args()
    
    # 设置日志
    setup_logger(
        level=args.log_level,
        log_file=args.log_file,
        console_output=not args.no_console
    )
    
    # 创建并启动代理
    agent = Agent(config_file=args.config)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        print("\n接收到中断信号，正在关闭代理...")
    except Exception as e:
        print(f"代理运行异常: {e}")
        sys.exit(1)
    finally:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())