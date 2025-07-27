"""
Unit tests for UDP protocol plugin.

Tests the UDP packet transmission functionality including configuration validation,
packet sending, and metrics calculation.
"""

import pytest
import asyncio
import socket
import struct
from unittest.mock import Mock, patch, AsyncMock

from agent.protocols.udp import UDPPlugin
from agent.protocols.base import (
    ProtocolConfig, ProtocolResult, ProtocolTestStatus, ProtocolType, ProtocolError
)


class TestUDPPlugin:
    """Test UDP protocol plugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = UDPPlugin()
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        assert self.plugin.name == 'udp'
        assert self.plugin.protocol_type == ProtocolType.UDP
        assert 'packet_count' in self.plugin.supported_parameters
        assert 'packet_size' in self.plugin.supported_parameters
        assert 'interval' in self.plugin.supported_parameters
        assert 'expect_response' in self.plugin.supported_parameters
    
    def test_default_config(self):
        """Test default configuration."""
        config = self.plugin.get_default_config()
        
        assert config['timeout'] == 5.0
        assert config['parameters']['packet_count'] == 5
        assert config['parameters']['packet_size'] == 64
        assert config['parameters']['interval'] == 1.0
        assert config['parameters']['expect_response'] is False
    
    def test_metrics_description(self):
        """Test metrics description."""
        metrics = self.plugin.get_metrics_description()
        
        expected_metrics = {
            'packets_sent', 'packets_received', 'transmission_errors',
            'response_rate', 'error_rate', 'min_response_time',
            'max_response_time', 'avg_response_time', 'stddev_response_time',
            'jitter', 'transmission_reliability'
        }
        
        assert set(metrics.keys()) == expected_metrics
        assert all(isinstance(desc, str) for desc in metrics.values())
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        config = ProtocolConfig(
            target='example.com',
            port=53,
            timeout=5.0,
            parameters={
                'packet_count': 5,
                'packet_size': 64,
                'interval': 1.0,
                'expect_response': True
            }
        )
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_minimal(self):
        """Test configuration validation with minimal config."""
        config = ProtocolConfig(target='example.com', port=53)
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_invalid_target(self):
        """Test configuration validation with invalid target."""
        config = ProtocolConfig(target='', port=53)
        
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
    
    def test_validate_config_invalid_packet_count(self):
        """Test configuration validation with invalid packet count."""
        config = ProtocolConfig(
            target='example.com',
            port=53,
            parameters={'packet_count': 0}
        )
        
        assert self.plugin.validate_config(config) is False
        
        config.parameters['packet_count'] = -1
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_packet_size(self):
        """Test configuration validation with invalid packet size."""
        config = ProtocolConfig(
            target='example.com',
            port=53,
            parameters={'packet_size': 0}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_interval(self):
        """Test configuration validation with invalid interval."""
        config = ProtocolConfig(
            target='example.com',
            port=53,
            parameters={'interval': -1.0}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_expect_response(self):
        """Test configuration validation with invalid expect_response."""
        config = ProtocolConfig(
            target='example.com',
            port=53,
            parameters={'expect_response': 'invalid'}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_create_packet_data(self):
        """Test packet data creation."""
        packet_data = self.plugin._create_packet_data(64, 1)
        
        assert len(packet_data) == 64
        
        # Verify header structure (sequence number + timestamp)
        sequence, timestamp = struct.unpack('!IQ', packet_data[:12])
        assert sequence == 1
        assert timestamp > 0
    
    def test_create_packet_data_small_size(self):
        """Test packet data creation with small size."""
        packet_data = self.plugin._create_packet_data(8, 2)
        
        # Should be at least header size (12 bytes) even if we requested 8
        # because header is always included
        assert len(packet_data) == 12  # Header size is 12 bytes minimum
    
    def test_calculate_metrics_empty_results(self):
        """Test metrics calculation with empty results."""
        metrics = self.plugin._calculate_metrics([], False)
        
        assert metrics['packets_sent'] == 0
        assert metrics['packets_received'] == 0
        assert metrics['transmission_errors'] == 0
        assert metrics['response_rate'] == 0.0
        assert metrics['error_rate'] == 0.0
        assert metrics['min_response_time'] is None
        assert metrics['max_response_time'] is None
        assert metrics['avg_response_time'] is None
        assert metrics['stddev_response_time'] is None
        assert metrics['jitter'] is None
        assert metrics['transmission_reliability'] == 0.0
    
    def test_calculate_metrics_all_sent_no_response_expected(self):
        """Test metrics calculation with all packets sent, no responses expected."""
        packet_results = [
            {'sent': True, 'response_received': None, 'response_time': None},
            {'sent': True, 'response_received': None, 'response_time': None},
            {'sent': True, 'response_received': None, 'response_time': None}
        ]
        
        metrics = self.plugin._calculate_metrics(packet_results, False)
        
        assert metrics['packets_sent'] == 3
        assert metrics['packets_received'] == 0
        assert metrics['transmission_errors'] == 0
        assert metrics['response_rate'] == 0.0
        assert metrics['error_rate'] == 0.0
        assert metrics['transmission_reliability'] == 100.0
    
    def test_calculate_metrics_with_transmission_errors(self):
        """Test metrics calculation with transmission errors."""
        packet_results = [
            {'sent': True, 'response_received': None, 'response_time': None},
            {'sent': False, 'transmission_error': 'Network unreachable'},
            {'sent': True, 'response_received': None, 'response_time': None}
        ]
        
        metrics = self.plugin._calculate_metrics(packet_results, False)
        
        assert metrics['packets_sent'] == 2
        assert metrics['transmission_errors'] == 1
        assert metrics['error_rate'] == 33.3  # 1 error out of 3 total packets
        assert metrics['transmission_reliability'] == 66.7
    
    def test_calculate_metrics_with_responses(self):
        """Test metrics calculation with responses expected."""
        packet_results = [
            {'sent': True, 'response_received': True, 'response_time': 10.0},
            {'sent': True, 'response_received': True, 'response_time': 15.0},
            {'sent': True, 'response_received': False, 'response_time': None},
            {'sent': True, 'response_received': True, 'response_time': 12.0}
        ]
        
        metrics = self.plugin._calculate_metrics(packet_results, True)
        
        assert metrics['packets_sent'] == 4
        assert metrics['packets_received'] == 3
        assert metrics['response_rate'] == 75.0
        assert metrics['min_response_time'] == 10.0
        assert metrics['max_response_time'] == 15.0
        assert metrics['avg_response_time'] == 12.33  # (10+15+12)/3
        assert metrics['stddev_response_time'] > 0
        assert metrics['jitter'] > 0
    
    def test_calculate_metrics_no_responses_received(self):
        """Test metrics calculation with no responses received."""
        packet_results = [
            {'sent': True, 'response_received': False, 'response_time': None},
            {'sent': True, 'response_received': False, 'response_time': None}
        ]
        
        metrics = self.plugin._calculate_metrics(packet_results, True)
        
        assert metrics['packets_sent'] == 2
        assert metrics['packets_received'] == 0
        assert metrics['response_rate'] == 0.0
        assert metrics['min_response_time'] is None
        assert metrics['max_response_time'] is None
        assert metrics['avg_response_time'] is None
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    async def test_send_udp_packet_success_no_response(self, mock_socket_class):
        """Test successful UDP packet sending without expecting response."""
        mock_sock = Mock()
        
        result = await self.plugin._send_udp_packet(
            mock_sock, '192.168.1.1', 53, 64, 1, 5.0, False
        )
        
        assert result['sequence'] == 1
        assert result['sent'] is True
        assert result['packet_size'] == 64
        assert result['transmission_error'] is None
        assert result['response_received'] is None
        assert result['response_time'] is None
        
        # Verify socket operations
        mock_sock.sendto.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    async def test_send_udp_packet_success_with_response(self, mock_socket_class):
        """Test successful UDP packet sending with response."""
        mock_sock = Mock()
        mock_sock.recvfrom.return_value = (b'response', ('192.168.1.1', 53))
        
        result = await self.plugin._send_udp_packet(
            mock_sock, '192.168.1.1', 53, 64, 1, 5.0, True
        )
        
        assert result['sequence'] == 1
        assert result['sent'] is True
        assert result['response_received'] is True
        assert result['response_time'] is not None
        assert result['response_size'] == 8
        assert result['response_from'] == '192.168.1.1'
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    async def test_send_udp_packet_response_timeout(self, mock_socket_class):
        """Test UDP packet sending with response timeout."""
        mock_sock = Mock()
        mock_sock.recvfrom.side_effect = socket.timeout()
        
        result = await self.plugin._send_udp_packet(
            mock_sock, '192.168.1.1', 53, 64, 1, 5.0, True
        )
        
        assert result['sequence'] == 1
        assert result['sent'] is True
        assert result['response_received'] is False
        assert result['response_time'] is None
        assert result['timeout'] is True
    
    @pytest.mark.asyncio
    @patch('socket.socket')
    async def test_send_udp_packet_transmission_error(self, mock_socket_class):
        """Test UDP packet sending with transmission error."""
        mock_sock = Mock()
        mock_sock.sendto.side_effect = socket.error("Network unreachable")
        
        result = await self.plugin._send_udp_packet(
            mock_sock, '192.168.1.1', 53, 64, 1, 5.0, False
        )
        
        assert result['sequence'] == 1
        assert result['sent'] is False
        assert result['transmission_error'] == "Network unreachable"
        assert result['response_received'] is None
    
    @pytest.mark.asyncio
    @patch('socket.gethostbyname')
    @patch('socket.socket')
    async def test_test_udp_packets_success(self, mock_socket_class, mock_gethostbyname):
        """Test UDP packet testing with multiple packets."""
        # Mock DNS resolution
        mock_gethostbyname.return_value = '192.168.1.1'
        
        # Mock socket
        mock_sock = Mock()
        mock_socket_class.return_value = mock_sock
        
        # Mock the _send_udp_packet method
        with patch.object(self.plugin, '_send_udp_packet') as mock_send:
            mock_send.side_effect = [
                {'sequence': 1, 'sent': True, 'response_received': None},
                {'sequence': 2, 'sent': True, 'response_received': None}
            ]
            
            results = await self.plugin._test_udp_packets(
                target='example.com',
                port=53,
                packet_count=2,
                packet_size=64,
                interval=0.1,  # Short interval for testing
                timeout=5.0,
                expect_response=False
            )
        
        assert len(results) == 2
        assert results[0]['sequence'] == 1
        assert results[1]['sequence'] == 2
        
        # Verify socket setup
        mock_sock.settimeout.assert_called_once_with(5.0)
        mock_sock.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('socket.gethostbyname')
    async def test_test_udp_packets_dns_failure(self, mock_gethostbyname):
        """Test UDP packet testing with DNS resolution failure."""
        mock_gethostbyname.side_effect = socket.gaierror("Name resolution failed")
        
        with pytest.raises(ProtocolError, match="DNS resolution failed"):
            await self.plugin._test_udp_packets(
                target='invalid.host',
                port=53,
                packet_count=1,
                packet_size=64,
                interval=1.0,
                timeout=5.0,
                expect_response=False
            )
    
    @pytest.mark.asyncio
    @patch.object(UDPPlugin, '_test_udp_packets')
    async def test_execute_success(self, mock_test_packets):
        """Test successful UDP test execution."""
        # Mock packet test results
        mock_test_packets.return_value = [
            {'sent': True, 'response_received': None, 'response_time': None, 'sequence': 1},
            {'sent': True, 'response_received': None, 'response_time': None, 'sequence': 2},
            {'sent': True, 'response_received': None, 'response_time': None, 'sequence': 3}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=53,
            timeout=5.0,
            parameters={'packet_count': 3}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'udp'
        assert result.target == 'example.com'
        assert result.port == 53
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.error_message is None
        assert result.metrics['packets_sent'] == 3
        assert result.metrics['transmission_errors'] == 0
        assert 'packet_results' in result.raw_data
    
    @pytest.mark.asyncio
    @patch.object(UDPPlugin, '_test_udp_packets')
    async def test_execute_no_responses_expected(self, mock_test_packets):
        """Test UDP test execution expecting responses but receiving none."""
        # Mock packet test results with no responses
        mock_test_packets.return_value = [
            {'sent': True, 'response_received': False, 'response_time': None, 'sequence': 1},
            {'sent': True, 'response_received': False, 'response_time': None, 'sequence': 2}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=53,
            timeout=5.0,
            parameters={'packet_count': 2, 'expect_response': True}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'udp'
        assert result.status == ProtocolTestStatus.FAILED
        assert result.error_message == "No responses received"
        assert result.metrics['response_rate'] == 0.0
    
    @pytest.mark.asyncio
    @patch.object(UDPPlugin, '_test_udp_packets')
    async def test_execute_high_transmission_errors(self, mock_test_packets):
        """Test UDP test execution with high transmission error rate."""
        # Mock packet test results with many transmission errors
        mock_test_packets.return_value = [
            {'sent': False, 'transmission_error': 'Network unreachable', 'sequence': 1},
            {'sent': False, 'transmission_error': 'Network unreachable', 'sequence': 2},
            {'sent': True, 'response_received': None, 'response_time': None, 'sequence': 3}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=53,
            timeout=5.0,
            parameters={'packet_count': 3}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'udp'
        assert result.status == ProtocolTestStatus.ERROR
        assert "High transmission error rate" in result.error_message
        assert result.metrics['error_rate'] == 66.7
    
    @pytest.mark.asyncio
    async def test_execute_invalid_config(self):
        """Test UDP test execution with invalid configuration."""
        config = ProtocolConfig(target='example.com')  # Missing port
        
        with pytest.raises(ProtocolError, match="Invalid configuration"):
            await self.plugin.execute(config)
    
    @pytest.mark.asyncio
    @patch.object(UDPPlugin, '_test_udp_packets')
    async def test_execute_exception(self, mock_test_packets):
        """Test UDP test execution when packet test raises exception."""
        mock_test_packets.side_effect = Exception("Network error")
        
        config = ProtocolConfig(target='example.com', port=53)
        
        with pytest.raises(ProtocolError, match="UDP test failed"):
            await self.plugin.execute(config)
    
    @pytest.mark.asyncio
    @patch.object(UDPPlugin, '_test_udp_packets')
    async def test_execute_custom_parameters(self, mock_test_packets):
        """Test UDP test execution with custom parameters."""
        mock_test_packets.return_value = [
            {'sent': True, 'response_received': True, 'response_time': 5.0, 'sequence': 1},
            {'sent': True, 'response_received': True, 'response_time': 6.0, 'sequence': 2}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            port=123,
            timeout=10.0,
            parameters={
                'packet_count': 2,
                'packet_size': 128,
                'interval': 0.5,
                'expect_response': True
            }
        )
        
        result = await self.plugin.execute(config)
        
        # Verify packet test was called with correct parameters
        mock_test_packets.assert_called_once_with(
            target='example.com',
            port=123,
            packet_count=2,
            packet_size=128,
            interval=0.5,
            timeout=10.0,
            expect_response=True
        )
        
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.port == 123
        assert result.raw_data['parameters']['packet_count'] == 2
        assert result.raw_data['parameters']['packet_size'] == 128
        assert result.raw_data['parameters']['interval'] == 0.5
        assert result.raw_data['parameters']['expect_response'] is True