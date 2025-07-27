"""
Unit tests for TCP protocol plugin.

Tests the TCP connection testing functionality including configuration validation,
connection testing, and metrics calculation.
"""

import pytest
import asyncio
import socket
from unittest.mock import Mock, patch, AsyncMock

from agent.protocols.tcp import TCPPlugin
from agent.protocols.base import (
    ProtocolConfig, ProtocolResult, ProtocolTestStatus, ProtocolType, ProtocolError
)


class TestTCPPlugin:
    """Test TCP protocol plugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = TCPPlugin()
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        assert self.plugin.name == 'tcp'
        assert self.plugin.protocol_type == ProtocolType.TCP
        assert 'connect_attempts' in self.plugin.supported_parameters
        assert 'retry_interval' in self.plugin.supported_parameters
        assert 'source_port' in self.plugin.supported_parameters
    
    def test_default_config(self):
        """Test default configuration."""
        config = self.plugin.get_default_config()
        
        assert config['timeout'] == 5.0
        assert config['parameters']['connect_attempts'] == 3
        assert config['parameters']['retry_interval'] == 1.0
        assert config['parameters']['source_port'] is None
    
    def test_metrics_description(self):
        """Test metrics description."""
        metrics = self.plugin.get_metrics_description()
        
        expected_metrics = {
            'total_attempts', 'successful_connections', 'failed_connections',
            'success_rate', 'min_connect_time', 'max_connect_time',
            'avg_connect_time', 'stddev_connect_time', 'connection_reliability'
        }
        
        assert set(metrics.keys()) == expected_metrics
        assert all(isinstance(desc, str) for desc in metrics.values())
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        config = ProtocolConfig(
            target='example.com',
            port=80,
            timeout=5.0,
            parameters={
                'connect_attempts': 3,
                'retry_interval': 1.0,
                'source_port': 12345
            }
        )
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_minimal(self):
        """Test configuration validation with minimal config."""
        config = ProtocolConfig(target='example.com', port=80)
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_invalid_target(self):
        """Test configuration validation with invalid target."""
        config = ProtocolConfig(target='', port=80)
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_missing_port(self):
        """Test configuration validation with missing port."""
        config = ProtocolConfig(target='example.com')
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_port(self):
        """Test configuration validation with invalid port."""
        config = ProtocolConfig(target='example.com', port=0)
        assert self.plugin.validate_config(config) is False
        
        config.port = 65536
        assert self.plugin.validate_config(config) is False
        
        config.port = -1
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_attempts(self):
        """Test configuration validation with invalid attempts."""
        config = ProtocolConfig(
            target='example.com',
            port=80,
            parameters={'connect_attempts': 0}
        )
        
        assert self.plugin.validate_config(config) is False
        
        config.parameters['connect_attempts'] = -1
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_retry_interval(self):
        """Test configuration validation with invalid retry interval."""
        config = ProtocolConfig(
            target='example.com',
            port=80,
            parameters={'retry_interval': -1.0}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_source_port(self):
        """Test configuration validation with invalid source port."""
        config = ProtocolConfig(
            target='example.com',
            port=80,
            parameters={'source_port': 0}
        )
        
        assert self.plugin.validate_config(config) is False
        
        config.parameters['source_port'] = 65536
        assert self.plugin.validate_config(config) is False
    
    def test_calculate_metrics_empty_results(self):
        """Test metrics calculation with empty results."""
        metrics = self.plugin._calculate_metrics([])
        
        assert metrics['total_attempts'] == 0
        assert metrics['successful_connections'] == 0
        assert metrics['failed_connections'] == 0
        assert metrics['success_rate'] == 0.0
        assert metrics['min_connect_time'] is None
        assert metrics['max_connect_time'] is None
        assert metrics['avg_connect_time'] is None
        assert metrics['stddev_connect_time'] is None
        assert metrics['connection_reliability'] == 0.0
    
    def test_calculate_metrics_all_successful(self):
        """Test metrics calculation with all successful connections."""
        connection_results = [
            {'success': True, 'connect_time': 10.0, 'error': None},
            {'success': True, 'connect_time': 15.0, 'error': None},
            {'success': True, 'connect_time': 20.0, 'error': None}
        ]
        
        metrics = self.plugin._calculate_metrics(connection_results)
        
        assert metrics['total_attempts'] == 3
        assert metrics['successful_connections'] == 3
        assert metrics['failed_connections'] == 0
        assert metrics['success_rate'] == 100.0
        assert metrics['min_connect_time'] == 10.0
        assert metrics['max_connect_time'] == 20.0
        assert metrics['avg_connect_time'] == 15.0
        assert metrics['stddev_connect_time'] > 0
        assert metrics['connection_reliability'] <= 100.0
    
    def test_calculate_metrics_mixed_results(self):
        """Test metrics calculation with mixed results."""
        connection_results = [
            {'success': True, 'connect_time': 10.0, 'error': None},
            {'success': False, 'connect_time': None, 'error': 'Connection refused'},
            {'success': True, 'connect_time': 20.0, 'error': None}
        ]
        
        metrics = self.plugin._calculate_metrics(connection_results)
        
        assert metrics['total_attempts'] == 3
        assert metrics['successful_connections'] == 2
        assert metrics['failed_connections'] == 1
        assert metrics['success_rate'] == 66.7
        assert metrics['min_connect_time'] == 10.0
        assert metrics['max_connect_time'] == 20.0
        assert metrics['avg_connect_time'] == 15.0
    
    def test_calculate_metrics_all_failed(self):
        """Test metrics calculation with all failed connections."""
        connection_results = [
            {'success': False, 'connect_time': None, 'error': 'Connection refused'},
            {'success': False, 'connect_time': None, 'error': 'Timeout'},
            {'success': False, 'connect_time': None, 'error': 'Host unreachable'}
        ]
        
        metrics = self.plugin._calculate_metrics(connection_results)
        
        assert metrics['total_attempts'] == 3
        assert metrics['successful_connections'] == 0
        assert metrics['failed_connections'] == 3
        assert metrics['success_rate'] == 0.0
        assert metrics['min_connect_time'] is None
        assert metrics['max_connect_time'] is None
        assert metrics['avg_connect_time'] is None
        assert metrics['stddev_connect_time'] is None
        assert metrics['connection_reliability'] == 0.0
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    @patch('socket.gethostbyname')
    async def test_single_tcp_connection_success(self, mock_gethostbyname, mock_socket):
        """Test successful single TCP connection."""
        # Mock DNS resolution
        mock_gethostbyname.return_value = '192.168.1.1'
        
        # Mock socket
        mock_sock = Mock()
        mock_socket.return_value = mock_sock
        
        result = await self.plugin._single_tcp_connection('example.com', 80, 5.0)
        
        assert result['success'] is True
        assert result['connect_time'] is not None
        assert result['error'] is None
        assert result['resolved_ip'] == '192.168.1.1'
        
        # Verify socket operations
        mock_sock.settimeout.assert_called_once_with(5.0)
        mock_sock.connect.assert_called_once_with(('192.168.1.1', 80))
        mock_sock.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    @patch('socket.gethostbyname')
    async def test_single_tcp_connection_dns_failure(self, mock_gethostbyname, mock_socket):
        """Test TCP connection with DNS resolution failure."""
        # Mock DNS resolution failure
        mock_gethostbyname.side_effect = socket.gaierror("Name resolution failed")
        
        result = await self.plugin._single_tcp_connection('invalid.host', 80, 5.0)
        
        assert result['success'] is False
        assert result['connect_time'] is None
        assert 'DNS resolution failed' in result['error']
        assert result['resolved_ip'] is None
        
        # Socket should not be created
        mock_socket.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    @patch('socket.gethostbyname')
    async def test_single_tcp_connection_timeout(self, mock_gethostbyname, mock_socket):
        """Test TCP connection timeout."""
        # Mock DNS resolution
        mock_gethostbyname.return_value = '192.168.1.1'
        
        # Mock socket timeout
        mock_sock = Mock()
        mock_sock.connect.side_effect = socket.timeout()
        mock_socket.return_value = mock_sock
        
        result = await self.plugin._single_tcp_connection('example.com', 80, 5.0)
        
        assert result['success'] is False
        assert result['connect_time'] is None
        assert 'Connection timeout' in result['error']
        assert result['resolved_ip'] == '192.168.1.1'
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    @patch('socket.gethostbyname')
    async def test_single_tcp_connection_refused(self, mock_gethostbyname, mock_socket):
        """Test TCP connection refused."""
        # Mock DNS resolution
        mock_gethostbyname.return_value = '192.168.1.1'
        
        # Mock socket connection refused
        mock_sock = Mock()
        mock_sock.connect.side_effect = socket.error("Connection refused")
        mock_socket.return_value = mock_sock
        
        result = await self.plugin._single_tcp_connection('example.com', 80, 5.0)
        
        assert result['success'] is False
        assert result['connect_time'] is None
        assert 'Connection failed' in result['error']
        assert result['resolved_ip'] == '192.168.1.1'
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    @patch('socket.gethostbyname')
    async def test_single_tcp_connection_with_source_port(self, mock_gethostbyname, mock_socket):
        """Test TCP connection with source port binding."""
        # Mock DNS resolution
        mock_gethostbyname.return_value = '192.168.1.1'
        
        # Mock socket
        mock_sock = Mock()
        mock_socket.return_value = mock_sock
        
        result = await self.plugin._single_tcp_connection('example.com', 80, 5.0, 12345)
        
        assert result['success'] is True
        
        # Verify source port binding
        mock_sock.bind.assert_called_once_with(('', 12345))
    
    @pytest.mark.asyncio
    @patch.object(TCPPlugin, '_single_tcp_connection')
    async def test_test_tcp_connection_multiple_attempts(self, mock_single_connection):
        """Test TCP connection with multiple attempts."""
        # Mock single connection results
        mock_single_connection.side_effect = [
            {'success': True, 'connect_time': 10.0, 'error': None, 'attempt': 1},
            {'success': False, 'connect_time': None, 'error': 'Timeout', 'attempt': 2},
            {'success': True, 'connect_time': 15.0, 'error': None, 'attempt': 3}
        ]
        
        results = await self.plugin._test_tcp_connection(
            target='example.com',
            port=80,
            timeout=5.0,
            attempts=3,
            retry_interval=0.1,  # Short interval for testing
            source_port=None
        )
        
        assert len(results) == 3
        assert results[0]['attempt'] == 1
        assert results[1]['attempt'] == 2
        assert results[2]['attempt'] == 3
        
        # Verify single connection was called 3 times
        assert mock_single_connection.call_count == 3
    
    @pytest.mark.asyncio
    @patch.object(TCPPlugin, '_test_tcp_connection')
    async def test_execute_success(self, mock_test_connection):
        """Test successful TCP test execution."""
        # Mock connection test results
        mock_test_connection.return_value = [
            {'success': True, 'connect_time': 10.0, 'error': None, 'attempt': 1},
            {'success': True, 'connect_time': 12.0, 'error': None, 'attempt': 2},
            {'success': True, 'connect_time': 11.0, 'error': None, 'attempt': 3}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=80,
            timeout=5.0,
            parameters={'connect_attempts': 3}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'tcp'
        assert result.target == 'example.com'
        assert result.port == 80
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.error_message is None
        assert result.metrics['successful_connections'] == 3
        assert result.metrics['success_rate'] == 100.0
        assert 'connection_results' in result.raw_data
    
    @pytest.mark.asyncio
    @patch.object(TCPPlugin, '_test_tcp_connection')
    async def test_execute_all_failed(self, mock_test_connection):
        """Test TCP test execution with all connections failed."""
        # Mock connection test results with all failures
        mock_test_connection.return_value = [
            {'success': False, 'connect_time': None, 'error': 'Connection refused', 'attempt': 1},
            {'success': False, 'connect_time': None, 'error': 'Connection refused', 'attempt': 2},
            {'success': False, 'connect_time': None, 'error': 'Connection refused', 'attempt': 3}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=80,
            timeout=5.0,
            parameters={'connect_attempts': 3}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'tcp'
        assert result.status == ProtocolTestStatus.FAILED
        assert result.error_message == "All connection attempts failed"
        assert result.metrics['successful_connections'] == 0
        assert result.metrics['success_rate'] == 0.0
    
    @pytest.mark.asyncio
    @patch.object(TCPPlugin, '_test_tcp_connection')
    async def test_execute_low_success_rate(self, mock_test_connection):
        """Test TCP test execution with low success rate."""
        # Mock connection test results with low success rate
        mock_test_connection.return_value = [
            {'success': True, 'connect_time': 10.0, 'error': None, 'attempt': 1},
            {'success': False, 'connect_time': None, 'error': 'Timeout', 'attempt': 2},
            {'success': False, 'connect_time': None, 'error': 'Timeout', 'attempt': 3}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=80,
            timeout=5.0,
            parameters={'connect_attempts': 3}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'tcp'
        assert result.status == ProtocolTestStatus.ERROR
        assert "Low success rate" in result.error_message
        assert result.metrics['success_rate'] == 33.3
    
    @pytest.mark.asyncio
    async def test_execute_invalid_config(self):
        """Test TCP test execution with invalid configuration."""
        config = ProtocolConfig(target='example.com')  # Missing port
        
        with pytest.raises(ProtocolError, match="Invalid configuration"):
            await self.plugin.execute(config)
    
    @pytest.mark.asyncio
    @patch.object(TCPPlugin, '_test_tcp_connection')
    async def test_execute_exception(self, mock_test_connection):
        """Test TCP test execution when connection test raises exception."""
        mock_test_connection.side_effect = Exception("Network error")
        
        config = ProtocolConfig(target='example.com', port=80)
        
        with pytest.raises(ProtocolError, match="TCP test failed"):
            await self.plugin.execute(config)
    
    @pytest.mark.asyncio
    @patch.object(TCPPlugin, '_test_tcp_connection')
    async def test_execute_custom_parameters(self, mock_test_connection):
        """Test TCP test execution with custom parameters."""
        mock_test_connection.return_value = [
            {'success': True, 'connect_time': 5.0, 'error': None, 'attempt': 1},
            {'success': True, 'connect_time': 6.0, 'error': None, 'attempt': 2}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=443,
            timeout=10.0,
            parameters={
                'connect_attempts': 2,
                'retry_interval': 0.5,
                'source_port': 12345
            }
        )
        
        result = await self.plugin.execute(config)
        
        # Verify connection test was called with correct parameters
        mock_test_connection.assert_called_once_with(
            target='example.com',
            port=443,
            timeout=10.0,
            attempts=2,
            retry_interval=0.5,
            source_port=12345
        )
        
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.port == 443
        assert result.raw_data['parameters']['connect_attempts'] == 2
        assert result.raw_data['parameters']['retry_interval'] == 0.5
        assert result.raw_data['parameters']['source_port'] == 12345