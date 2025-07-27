"""代理配置管理模块"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from shared.config import AgentConfig

logger = logging.getLogger(__name__)


class AgentConfigManager:
    """代理配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径，默认为 ~/.agent/config.json
        """
        self.config_file = config_file or self._get_default_config_path()
        self._config = AgentConfig()
        self._local_config: Dict[str, Any] = {}
        self._load_local_config()
    
    def _get_default_config_path(self) -> str:
        """获取默认配置文件路径"""
        home_dir = Path.home()
        config_dir = home_dir / ".agent"
        config_dir.mkdir(exist_ok=True)
        return str(config_dir / "config.json")
    
    def _load_local_config(self):
        """加载本地配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._local_config = json.load(f)
                logger.info(f"已加载本地配置文件: {self.config_file}")
            else:
                logger.info("本地配置文件不存在，使用默认配置")
        except Exception as e:
            logger.error(f"加载本地配置文件失败: {e}")
            self._local_config = {}
    
    def save_local_config(self):
        """保存本地配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self._local_config, f, indent=2, ensure_ascii=False)
            logger.info(f"本地配置已保存到: {self.config_file}")
        except Exception as e:
            logger.error(f"保存本地配置文件失败: {e}")
            raise
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        # 优先从本地配置获取
        if key in self._local_config:
            return self._local_config[key]
        
        # 从环境变量配置获取
        if hasattr(self._config, key):
            return getattr(self._config, key)
        
        return default
    
    def set(self, key: str, value: Any):
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        self._local_config[key] = value
    
    def update(self, config_dict: Dict[str, Any]):
        """
        批量更新配置
        
        Args:
            config_dict: 配置字典
        """
        self._local_config.update(config_dict)
    
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        result = {}
        
        # 先添加环境变量配置
        for field_name in self._config.__class__.model_fields:
            result[field_name] = getattr(self._config, field_name)
        
        # 再添加本地配置（覆盖环境变量配置）
        result.update(self._local_config)
        
        return result
    
    @property
    def agent_id(self) -> Optional[str]:
        """代理ID"""
        return self.get('agent_id') or self._config.agent_id
    
    @agent_id.setter
    def agent_id(self, value: str):
        """设置代理ID"""
        self.set('agent_id', value)
    
    @property
    def agent_name(self) -> str:
        """代理名称"""
        return self.get('agent_name') or self._config.agent_name
    
    @agent_name.setter
    def agent_name(self, value: str):
        """设置代理名称"""
        self.set('agent_name', value)
    
    @property
    def server_url(self) -> str:
        """服务器URL"""
        return self.get('server_url') or self._config.server_url
    
    @server_url.setter
    def server_url(self, value: str):
        """设置服务器URL"""
        self.set('server_url', value)
    
    @property
    def api_key(self) -> str:
        """API密钥"""
        return self.get('api_key') or self._config.api_key
    
    @api_key.setter
    def api_key(self, value: str):
        """设置API密钥"""
        self.set('api_key', value)
    
    @property
    def heartbeat_interval(self) -> int:
        """心跳间隔（秒）"""
        return self.get('heartbeat_interval') or self._config.heartbeat_interval
    
    @property
    def resource_report_interval(self) -> int:
        """资源报告间隔（秒）"""
        return self.get('resource_report_interval') or self._config.resource_report_interval
    
    @property
    def max_concurrent_tasks(self) -> int:
        """最大并发任务数"""
        return self.get('max_concurrent_tasks') or self._config.max_concurrent_tasks
    
    @property
    def task_timeout(self) -> int:
        """任务超时时间（秒）"""
        return self.get('task_timeout') or self._config.task_timeout
    
    @property
    def cert_file(self) -> Optional[str]:
        """证书文件路径"""
        return self.get('cert_file') or self._config.cert_file
    
    @property
    def key_file(self) -> Optional[str]:
        """私钥文件路径"""
        return self.get('key_file') or self._config.key_file
    
    @property
    def default_task_timeout(self) -> int:
        """默认任务超时时间（秒）"""
        return self.get('default_task_timeout', 30)
    
    @property
    def result_batch_size(self) -> int:
        """结果批量大小"""
        return self.get('result_batch_size', 10)
    
    @property
    def result_batch_timeout(self) -> int:
        """结果批量超时时间（秒）"""
        return self.get('result_batch_timeout', 30)