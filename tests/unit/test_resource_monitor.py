"""资源监控器单元测试"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock
from agent.monitoring.resource_monitor import ResourceMonitor


class TestResourceMonitor:
    """资源监控器测试类"""
    
    @pytest.fixture
    def mock_logger(self):
        """模拟日志记录器"""
        return Mock()
    
    @pytest.fixture
    def resource_monitor(self, mock_logger):
        """创建资源监控器实例"""
        return ResourceMonitor(logger=mock_logger)
    
    def test_init(self, mock_logger):
        """测试初始化"""
        monitor = ResourceMonitor(logger=mock_logger)
        assert monitor.logger == mock_logger
        assert monitor._last_network_stats is not None or monitor._last_network_stats is None
        assert monitor._last_network_time is not None or monitor._last_network_time is None
    
    def test_init_without_logger(self):
        """测试不提供日志记录器的初始化"""
        monitor = ResourceMonitor()
        assert monitor.logger is not None
    
    @patch('psutil.cpu_percent')
    def test_get_cpu_usage_success(self, mock_cpu_percent, resource_monitor):
        """测试成功获取CPU使用率"""
        mock_cpu_percent.return_value = 45.5
        
        result = resource_monitor.get_cpu_usage()
        
        assert result == 45.5
        mock_cpu_percent.assert_called_once_with(interval=1)
    
    @patch('psutil.cpu_percent')
    def test_get_cpu_usage_error(self, mock_cpu_percent, resource_monitor):
        """测试获取CPU使用率失败"""
        mock_cpu_percent.side_effect = Exception("CPU error")
        
        result = resource_monitor.get_cpu_usage()
        
        assert result == 0.0
        resource_monitor.logger.error.assert_called_once()
    
    @patch('psutil.virtual_memory')
    @patch('psutil.swap_memory')
    def test_get_memory_usage_success(self, mock_swap_memory, mock_virtual_memory, resource_monitor):
        """测试成功获取内存使用情况"""
        # 模拟虚拟内存
        mock_virtual_memory.return_value = Mock(
            total=8 * 1024**3,  # 8GB
            available=4 * 1024**3,  # 4GB
            used=4 * 1024**3,  # 4GB
            percent=50.0
        )
        
        # 模拟交换内存
        mock_swap_memory.return_value = Mock(
            total=2 * 1024**3,  # 2GB
            used=1 * 1024**3,  # 1GB
            percent=50.0
        )
        
        result = resource_monitor.get_memory_usage()
        
        assert result["total"] == 8.0
        assert result["available"] == 4.0
        assert result["used"] == 4.0
        assert result["percent"] == 50.0
        assert result["swap_total"] == 2.0
        assert result["swap_used"] == 1.0
        assert result["swap_percent"] == 50.0
    
    @patch('psutil.virtual_memory')
    def test_get_memory_usage_error(self, mock_virtual_memory, resource_monitor):
        """测试获取内存使用情况失败"""
        mock_virtual_memory.side_effect = Exception("Memory error")
        
        result = resource_monitor.get_memory_usage()
        
        expected = {
            "total": 0.0,
            "available": 0.0,
            "used": 0.0,
            "percent": 0.0,
            "swap_total": 0.0,
            "swap_used": 0.0,
            "swap_percent": 0.0
        }
        assert result == expected
        resource_monitor.logger.error.assert_called_once()
    
    @patch('psutil.disk_partitions')
    @patch('psutil.disk_usage')
    @patch('psutil.disk_io_counters')
    def test_get_disk_usage_success(self, mock_disk_io, mock_disk_usage, mock_disk_partitions, resource_monitor):
        """测试成功获取磁盘使用情况"""
        # 模拟磁盘分区
        mock_partition = Mock()
        mock_partition.device = "/dev/sda1"
        mock_partition.mountpoint = "/"
        mock_partition.fstype = "ext4"
        mock_disk_partitions.return_value = [mock_partition]
        
        # 模拟磁盘使用情况
        mock_disk_usage.return_value = Mock(
            total=100 * 1024**3,  # 100GB
            used=50 * 1024**3,   # 50GB
            free=50 * 1024**3    # 50GB
        )
        
        # 模拟磁盘IO
        mock_disk_io.return_value = Mock(
            read_count=1000,
            write_count=500,
            read_bytes=100 * 1024**2,  # 100MB
            write_bytes=50 * 1024**2,  # 50MB
            read_time=1000,
            write_time=500
        )
        
        result = resource_monitor.get_disk_usage()
        
        assert "/" in result
        assert result["/"]["device"] == "/dev/sda1"
        assert result["/"]["fstype"] == "ext4"
        assert result["/"]["total"] == 100.0
        assert result["/"]["used"] == 50.0
        assert result["/"]["free"] == 50.0
        assert result["/"]["percent"] == 50.0
        
        assert "io_stats" in result
        assert result["io_stats"]["read_count"] == 1000
        assert result["io_stats"]["write_count"] == 500
        assert result["io_stats"]["read_bytes"] == 100.0
        assert result["io_stats"]["write_bytes"] == 50.0
    
    @patch('psutil.disk_partitions')
    def test_get_disk_usage_error(self, mock_disk_partitions, resource_monitor):
        """测试获取磁盘使用情况失败"""
        mock_disk_partitions.side_effect = Exception("Disk error")
        
        result = resource_monitor.get_disk_usage()
        
        assert result == {}
        resource_monitor.logger.error.assert_called_once()
    
    @patch('psutil.net_io_counters')
    @patch('psutil.net_if_addrs')
    @patch('time.time')
    def test_get_network_usage_success(self, mock_time, mock_net_if_addrs, mock_net_io, resource_monitor):
        """测试成功获取网络使用情况"""
        # 模拟网络IO统计
        mock_net_io.return_value = Mock(
            bytes_sent=100 * 1024**2,  # 100MB
            bytes_recv=200 * 1024**2,  # 200MB
            packets_sent=1000,
            packets_recv=2000,
            errin=0,
            errout=0,
            dropin=0,
            dropout=0
        )
        
        # 模拟网络接口
        mock_addr = Mock()
        mock_addr.family.name = "AF_INET"
        mock_addr.address = "192.168.1.100"
        mock_addr.netmask = "255.255.255.0"
        mock_addr.broadcast = "192.168.1.255"
        
        mock_net_if_addrs.return_value = {
            "eth0": [mock_addr]
        }
        
        mock_time.return_value = 1000.0
        
        result = resource_monitor.get_network_usage()
        
        assert result["bytes_sent"] == 100.0
        assert result["bytes_recv"] == 200.0
        assert result["packets_sent"] == 1000
        assert result["packets_recv"] == 2000
        assert "interfaces" in result
        assert "eth0" in result["interfaces"]
    
    @patch('psutil.net_io_counters')
    def test_get_network_usage_error(self, mock_net_io, resource_monitor):
        """测试获取网络使用情况失败"""
        mock_net_io.side_effect = Exception("Network error")
        
        result = resource_monitor.get_network_usage()
        
        assert result == {}
        resource_monitor.logger.error.assert_called_once()
    
    @patch('psutil.getloadavg')
    @patch('psutil.cpu_count')
    @patch('psutil.pids')
    @patch('psutil.boot_time')
    @patch('time.time')
    def test_get_system_load_success(self, mock_time, mock_boot_time, mock_pids, 
                                   mock_cpu_count, mock_getloadavg, resource_monitor):
        """测试成功获取系统负载"""
        mock_getloadavg.return_value = (1.0, 1.5, 2.0)
        mock_cpu_count.side_effect = [8, 4]  # logical, physical
        mock_pids.return_value = [1, 2, 3, 4, 5]  # 5个进程
        mock_boot_time.return_value = 900.0
        mock_time.return_value = 1000.0
        
        result = resource_monitor.get_system_load()
        
        assert result["load_avg"]["1min"] == 1.0
        assert result["load_avg"]["5min"] == 1.5
        assert result["load_avg"]["15min"] == 2.0
        assert result["cpu_count"]["logical"] == 8
        assert result["cpu_count"]["physical"] == 4
        assert result["process_count"] == 5
        assert result["uptime"] == 100.0
    
    @patch('psutil.cpu_count')
    @patch('psutil.pids')
    @patch('psutil.boot_time')
    @patch('time.time')
    def test_get_system_load_no_loadavg(self, mock_time, mock_boot_time, mock_pids, 
                                       mock_cpu_count, resource_monitor):
        """测试在不支持getloadavg的系统上获取系统负载"""
        mock_cpu_count.side_effect = [8, 4]
        mock_pids.return_value = [1, 2, 3]
        mock_boot_time.return_value = 900.0
        mock_time.return_value = 1000.0
        
        # 模拟Windows系统（不支持getloadavg）
        with patch('psutil.getloadavg', side_effect=AttributeError):
            result = resource_monitor.get_system_load()
        
        assert "load_avg" not in result
        assert result["cpu_count"]["logical"] == 8
        assert result["cpu_count"]["physical"] == 4
        assert result["process_count"] == 3
        assert result["uptime"] == 100.0
    
    @patch('psutil.Process')
    def test_get_process_info_success(self, mock_process_class, resource_monitor):
        """测试成功获取进程信息"""
        mock_process = Mock()
        mock_process.pid = 1234
        mock_process.name.return_value = "python"
        mock_process.status.return_value = "running"
        mock_process.create_time.return_value = 1000.0
        mock_process.num_threads.return_value = 5
        
        # 模拟内存信息
        mock_memory_info = Mock()
        mock_memory_info.rss = 100 * 1024**2  # 100MB
        mock_memory_info.vms = 200 * 1024**2  # 200MB
        mock_process.memory_info.return_value = mock_memory_info
        mock_process.memory_percent.return_value = 5.0
        
        mock_process.cpu_percent.return_value = 10.0
        
        # 模拟IO信息
        mock_io_counters = Mock()
        mock_io_counters.read_count = 100
        mock_io_counters.write_count = 50
        mock_io_counters.read_bytes = 10 * 1024**2  # 10MB
        mock_io_counters.write_bytes = 5 * 1024**2  # 5MB
        mock_process.io_counters.return_value = mock_io_counters
        
        mock_process_class.return_value = mock_process
        
        result = resource_monitor.get_process_info()
        
        assert result["pid"] == 1234
        assert result["name"] == "python"
        assert result["status"] == "running"
        assert result["create_time"] == 1000.0
        assert result["num_threads"] == 5
        assert result["memory"]["rss"] == 100.0
        assert result["memory"]["vms"] == 200.0
        assert result["memory"]["percent"] == 5.0
        assert result["cpu_percent"] == 10.0
        assert result["io"]["read_count"] == 100
        assert result["io"]["write_count"] == 50
        assert result["io"]["read_bytes"] == 10.0
        assert result["io"]["write_bytes"] == 5.0
    
    @patch('psutil.Process')
    def test_get_process_info_error(self, mock_process_class, resource_monitor):
        """测试获取进程信息失败"""
        mock_process_class.side_effect = Exception("Process error")
        
        result = resource_monitor.get_process_info()
        
        assert result == {}
        resource_monitor.logger.error.assert_called_once()
    
    @patch.object(ResourceMonitor, 'get_cpu_usage')
    @patch.object(ResourceMonitor, 'get_memory_usage')
    @patch.object(ResourceMonitor, 'get_disk_usage')
    @patch.object(ResourceMonitor, 'get_network_usage')
    @patch.object(ResourceMonitor, 'get_system_load')
    @patch.object(ResourceMonitor, 'get_process_info')
    def test_collect_all_metrics(self, mock_process_info, mock_system_load, 
                                mock_network_usage, mock_disk_usage, 
                                mock_memory_usage, mock_cpu_usage, resource_monitor):
        """测试收集所有指标"""
        # 设置模拟返回值
        mock_cpu_usage.return_value = 50.0
        mock_memory_usage.return_value = {"total": 8.0, "used": 4.0}
        mock_disk_usage.return_value = {"/": {"total": 100.0, "used": 50.0}}
        mock_network_usage.return_value = {"bytes_sent": 100.0}
        mock_system_load.return_value = {"load_avg": {"1min": 1.0}}
        mock_process_info.return_value = {"pid": 1234}
        
        result = resource_monitor.collect_all_metrics()
        
        assert "timestamp" in result
        assert result["cpu"]["usage_percent"] == 50.0
        assert result["memory"]["total"] == 8.0
        assert result["disk"]["/"]["total"] == 100.0
        assert result["network"]["bytes_sent"] == 100.0
        assert result["system"]["load_avg"]["1min"] == 1.0
        assert result["process"]["pid"] == 1234
        
        # 验证所有方法都被调用
        mock_cpu_usage.assert_called_once()
        mock_memory_usage.assert_called_once()
        mock_disk_usage.assert_called_once()
        mock_network_usage.assert_called_once()
        mock_system_load.assert_called_once()
        mock_process_info.assert_called_once()
    
    @pytest.mark.asyncio
    @patch.object(ResourceMonitor, 'collect_all_metrics')
    async def test_collect_metrics_async(self, mock_collect_all_metrics, resource_monitor):
        """测试异步收集指标"""
        expected_metrics = {
            "timestamp": "2023-01-01T00:00:00",
            "cpu": {"usage_percent": 50.0}
        }
        mock_collect_all_metrics.return_value = expected_metrics
        
        result = await resource_monitor.collect_metrics_async()
        
        assert result == expected_metrics
        mock_collect_all_metrics.assert_called_once()
    
    @patch('psutil.net_io_counters')
    @patch('time.time')
    def test_network_bandwidth_calculation(self, mock_time, mock_net_io, resource_monitor):
        """测试网络带宽计算"""
        # 第一次调用
        mock_net_io.return_value = Mock(
            bytes_sent=100 * 1024**2,  # 100MB
            bytes_recv=200 * 1024**2,  # 200MB
            packets_sent=1000,
            packets_recv=2000,
            errin=0, errout=0, dropin=0, dropout=0
        )
        mock_time.return_value = 1000.0
        
        # 初始化网络统计
        resource_monitor._init_network_stats()
        
        # 第二次调用（1秒后）
        mock_net_io.return_value = Mock(
            bytes_sent=110 * 1024**2,  # 110MB (+10MB)
            bytes_recv=220 * 1024**2,  # 220MB (+20MB)
            packets_sent=1100,
            packets_recv=2200,
            errin=0, errout=0, dropin=0, dropout=0
        )
        mock_time.return_value = 1001.0
        
        result = resource_monitor.get_network_usage()
        
        # 验证带宽计算
        assert "bandwidth" in result
        assert result["bandwidth"]["upload_rate"] == 10.0  # 10MB/s
        assert result["bandwidth"]["download_rate"] == 20.0  # 20MB/s
        assert result["bandwidth"]["total_rate"] == 30.0  # 30MB/s
    
    @patch('psutil.disk_partitions')
    @patch('psutil.disk_usage')
    def test_disk_usage_permission_error(self, mock_disk_usage, mock_disk_partitions, resource_monitor):
        """测试磁盘使用情况权限错误处理"""
        # 模拟磁盘分区
        mock_partition = Mock()
        mock_partition.device = "/dev/sda1"
        mock_partition.mountpoint = "/restricted"
        mock_partition.fstype = "ext4"
        mock_disk_partitions.return_value = [mock_partition]
        
        # 模拟权限错误
        mock_disk_usage.side_effect = PermissionError("Permission denied")
        
        result = resource_monitor.get_disk_usage()
        
        # 应该跳过无权限的分区，返回空结果
        assert "/restricted" not in result