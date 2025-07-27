"""资源监控模块"""

import asyncio
import psutil
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime


class ResourceMonitor:
    """系统资源监控器"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        初始化资源监控器
        
        Args:
            logger: 日志记录器
        """
        self.logger = logger or logging.getLogger(__name__)
        self._last_network_stats = None
        self._last_network_time = None
        
        # 初始化网络统计
        self._init_network_stats()
    
    def _init_network_stats(self):
        """初始化网络统计数据"""
        try:
            self._last_network_stats = psutil.net_io_counters()
            self._last_network_time = time.time()
        except Exception as e:
            self.logger.warning(f"初始化网络统计失败: {e}")
            self._last_network_stats = None
            self._last_network_time = None
    
    def get_cpu_usage(self) -> float:
        """
        获取CPU使用率
        
        Returns:
            CPU使用率百分比 (0-100)
        """
        try:
            # 使用interval参数获取更准确的CPU使用率
            return psutil.cpu_percent(interval=1)
        except Exception as e:
            self.logger.error(f"获取CPU使用率失败: {e}")
            return 0.0
    
    def get_memory_usage(self) -> Dict[str, float]:
        """
        获取内存使用情况
        
        Returns:
            包含内存使用信息的字典
        """
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                "total": memory.total / (1024 ** 3),  # GB
                "available": memory.available / (1024 ** 3),  # GB
                "used": memory.used / (1024 ** 3),  # GB
                "percent": memory.percent,
                "swap_total": swap.total / (1024 ** 3),  # GB
                "swap_used": swap.used / (1024 ** 3),  # GB
                "swap_percent": swap.percent
            }
        except Exception as e:
            self.logger.error(f"获取内存使用情况失败: {e}")
            return {
                "total": 0.0,
                "available": 0.0,
                "used": 0.0,
                "percent": 0.0,
                "swap_total": 0.0,
                "swap_used": 0.0,
                "swap_percent": 0.0
            }
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """
        获取磁盘使用情况
        
        Returns:
            包含磁盘使用信息的字典
        """
        try:
            disk_usage = {}
            
            # 获取所有磁盘分区
            partitions = psutil.disk_partitions()
            
            for partition in partitions:
                try:
                    partition_usage = psutil.disk_usage(partition.mountpoint)
                    disk_usage[partition.mountpoint] = {
                        "device": partition.device,
                        "fstype": partition.fstype,
                        "total": partition_usage.total / (1024 ** 3),  # GB
                        "used": partition_usage.used / (1024 ** 3),  # GB
                        "free": partition_usage.free / (1024 ** 3),  # GB
                        "percent": (partition_usage.used / partition_usage.total) * 100
                    }
                except PermissionError:
                    # 跳过无权限访问的分区
                    continue
                except Exception as e:
                    self.logger.warning(f"获取分区 {partition.mountpoint} 使用情况失败: {e}")
                    continue
            
            # 获取磁盘IO统计
            try:
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    disk_usage["io_stats"] = {
                        "read_count": disk_io.read_count,
                        "write_count": disk_io.write_count,
                        "read_bytes": disk_io.read_bytes / (1024 ** 2),  # MB
                        "write_bytes": disk_io.write_bytes / (1024 ** 2),  # MB
                        "read_time": disk_io.read_time,
                        "write_time": disk_io.write_time
                    }
            except Exception as e:
                self.logger.warning(f"获取磁盘IO统计失败: {e}")
            
            return disk_usage
            
        except Exception as e:
            self.logger.error(f"获取磁盘使用情况失败: {e}")
            return {}
    
    def get_network_usage(self) -> Dict[str, Any]:
        """
        获取网络使用情况
        
        Returns:
            包含网络使用信息的字典
        """
        try:
            current_stats = psutil.net_io_counters()
            current_time = time.time()
            
            network_info = {
                "bytes_sent": current_stats.bytes_sent / (1024 ** 2),  # MB
                "bytes_recv": current_stats.bytes_recv / (1024 ** 2),  # MB
                "packets_sent": current_stats.packets_sent,
                "packets_recv": current_stats.packets_recv,
                "errin": current_stats.errin,
                "errout": current_stats.errout,
                "dropin": current_stats.dropin,
                "dropout": current_stats.dropout
            }
            
            # 计算网络带宽使用率（如果有上次的统计数据）
            if self._last_network_stats and self._last_network_time:
                time_delta = current_time - self._last_network_time
                if time_delta > 0:
                    bytes_sent_rate = (current_stats.bytes_sent - self._last_network_stats.bytes_sent) / time_delta
                    bytes_recv_rate = (current_stats.bytes_recv - self._last_network_stats.bytes_recv) / time_delta
                    
                    network_info["bandwidth"] = {
                        "upload_rate": bytes_sent_rate / (1024 ** 2),  # MB/s
                        "download_rate": bytes_recv_rate / (1024 ** 2),  # MB/s
                        "total_rate": (bytes_sent_rate + bytes_recv_rate) / (1024 ** 2)  # MB/s
                    }
            
            # 更新上次统计数据
            self._last_network_stats = current_stats
            self._last_network_time = current_time
            
            # 获取网络接口信息
            try:
                interfaces = {}
                for interface_name, interface_addresses in psutil.net_if_addrs().items():
                    interface_info = []
                    for addr in interface_addresses:
                        if addr.family.name in ['AF_INET', 'AF_INET6']:
                            interface_info.append({
                                "family": addr.family.name,
                                "address": addr.address,
                                "netmask": addr.netmask,
                                "broadcast": addr.broadcast
                            })
                    if interface_info:
                        interfaces[interface_name] = interface_info
                
                network_info["interfaces"] = interfaces
            except Exception as e:
                self.logger.warning(f"获取网络接口信息失败: {e}")
            
            return network_info
            
        except Exception as e:
            self.logger.error(f"获取网络使用情况失败: {e}")
            return {}
    
    def get_system_load(self) -> Dict[str, float]:
        """
        获取系统负载
        
        Returns:
            包含系统负载信息的字典
        """
        try:
            load_info = {}
            
            # 获取系统负载平均值（仅在Unix系统上可用）
            try:
                load_avg = psutil.getloadavg()
                load_info["load_avg"] = {
                    "1min": load_avg[0],
                    "5min": load_avg[1],
                    "15min": load_avg[2]
                }
            except AttributeError:
                # Windows系统不支持getloadavg
                pass
            
            # 获取CPU核心数
            load_info["cpu_count"] = {
                "logical": psutil.cpu_count(logical=True),
                "physical": psutil.cpu_count(logical=False)
            }
            
            # 获取进程数量
            load_info["process_count"] = len(psutil.pids())
            
            # 获取系统启动时间
            boot_time = psutil.boot_time()
            load_info["uptime"] = time.time() - boot_time
            
            return load_info
            
        except Exception as e:
            self.logger.error(f"获取系统负载失败: {e}")
            return {}
    
    def get_process_info(self) -> Dict[str, Any]:
        """
        获取当前进程信息
        
        Returns:
            包含进程信息的字典
        """
        try:
            process = psutil.Process()
            
            # 获取进程基本信息
            process_info = {
                "pid": process.pid,
                "name": process.name(),
                "status": process.status(),
                "create_time": process.create_time(),
                "num_threads": process.num_threads()
            }
            
            # 获取进程资源使用情况
            try:
                memory_info = process.memory_info()
                process_info["memory"] = {
                    "rss": memory_info.rss / (1024 ** 2),  # MB
                    "vms": memory_info.vms / (1024 ** 2),  # MB
                    "percent": process.memory_percent()
                }
            except Exception as e:
                self.logger.warning(f"获取进程内存信息失败: {e}")
            
            try:
                process_info["cpu_percent"] = process.cpu_percent()
            except Exception as e:
                self.logger.warning(f"获取进程CPU使用率失败: {e}")
            
            try:
                io_counters = process.io_counters()
                process_info["io"] = {
                    "read_count": io_counters.read_count,
                    "write_count": io_counters.write_count,
                    "read_bytes": io_counters.read_bytes / (1024 ** 2),  # MB
                    "write_bytes": io_counters.write_bytes / (1024 ** 2)  # MB
                }
            except Exception as e:
                self.logger.warning(f"获取进程IO信息失败: {e}")
            
            return process_info
            
        except Exception as e:
            self.logger.error(f"获取进程信息失败: {e}")
            return {}
    
    def collect_all_metrics(self) -> Dict[str, Any]:
        """
        收集所有资源指标
        
        Returns:
            包含所有资源指标的字典
        """
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "usage_percent": self.get_cpu_usage()
            },
            "memory": self.get_memory_usage(),
            "disk": self.get_disk_usage(),
            "network": self.get_network_usage(),
            "system": self.get_system_load(),
            "process": self.get_process_info()
        }
        
        return metrics
    
    async def collect_metrics_async(self) -> Dict[str, Any]:
        """
        异步收集资源指标
        
        Returns:
            包含所有资源指标的字典
        """
        # 在线程池中执行CPU密集型操作
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.collect_all_metrics)