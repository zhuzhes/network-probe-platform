"""
Unit tests for ICMP protocol plugin.

Tests the ICMP ping functionality including configuration validation,
ping execution, and metrics calculation.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from agent.protocols.icmp import ICMPPlugin
from agent.protocols.base import (
    ProtocolConfig, ProtocolResult, ProtocolTestStatus, ProtocolType, ProtocolError
)


class TestICMPPlugin:
    """Test ICMP protocol plugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = ICMPPlugin()
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        assert self.plugin.name == 'icmp'
        assert self.plugin.protocol_type == ProtocolType.ICMP
        assert 'count' in self.plugin.supported_parameters
        assert 'interval' in self.plugin.supported_parameters
        assert 'packet_size' in self.plugin.supported_parameters
        assert 'ttl' in self.plugin.supported_parameters
    
    def test_default_config(self):
        """Test default configuration."""
        config = self.plugin.get_default_config()
        
        assert config['timeout'] == 5.0
        assert config['parameters']['count'] == 4
        assert config['parameters']['interval'] == 1.0
        assert config['parameters']['packet_size'] == 32
        assert config['parameters']['ttl'] == 64
    
    def test_metrics_description(self):
        """Test metrics description."""
        metrics = self.plugin.get_metrics_description()
        
        expected_metrics = {
            'packets_sent', 'packets_received', 'packet_loss',
            'min_rtt', 'max_rtt', 'avg_rtt', 'stddev_rtt', 'jitter'
        }
        
        assert set(metrics.keys()) == expected_metrics
        assert all(isinstance(desc, str) for desc in metrics.values())
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        config = ProtocolConfig(
            target='8.8.8.8',
            timeout=5.0,
            parameters={
                'count': 4,
                'interval': 1.0,
                'packet_size': 64,
                'ttl': 64
            }
        )
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_minimal(self):
        """Test configuration validation with minimal config."""
        config = ProtocolConfig(target='8.8.8.8')
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_invalid_target(self):
        """Test configuration validation with invalid target."""
        config = ProtocolConfig(target='')
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_count(self):
        """Test configuration validation with invalid count."""
        config = ProtocolConfig(
            target='8.8.8.8',
            parameters={'count': 0}
        )
        
        assert self.plugin.validate_config(config) is False
        
        config.parameters['count'] = -1
        assert self.plugin.validate_config(config) is False
        
        config.parameters['count'] = 'invalid'
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_interval(self):
        """Test configuration validation with invalid interval."""
        config = ProtocolConfig(
            target='8.8.8.8',
            parameters={'interval': 0}
        )
        
        assert self.plugin.validate_config(config) is False
        
        config.parameters['interval'] = -1.0
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_packet_size(self):
        """Test configuration validation with invalid packet size."""
        config = ProtocolConfig(
            target='8.8.8.8',
            parameters={'packet_size': 0}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_ttl(self):
        """Test configuration validation with invalid TTL."""
        config = ProtocolConfig(
            target='8.8.8.8',
            parameters={'ttl': 0}
        )
        
        assert self.plugin.validate_config(config) is False
        
        config.parameters['ttl'] = 256
        assert self.plugin.validate_config(config) is False
    
    def test_calculate_metrics_empty_results(self):
        """Test metrics calculation with empty results."""
        metrics = self.plugin._calculate_metrics([])
        
        assert metrics['packets_sent'] == 0
        assert metrics['packets_received'] == 0
        assert metrics['packet_loss'] == 100.0
        assert metrics['min_rtt'] is None
        assert metrics['max_rtt'] is None
        assert metrics['avg_rtt'] is None
        assert metrics['stddev_rtt'] is None
        assert metrics['jitter'] is None
    
    def test_calculate_metrics_single_result(self):
        """Test metrics calculation with single result."""
        ping_results = [{'rtt': 20.5, 'timestamp': 1234567890}]
        metrics = self.plugin._calculate_metrics(ping_results)
        
        assert metrics['packets_sent'] == 4  # Estimated
        assert metrics['packets_received'] == 1
        assert metrics['packet_loss'] == 75.0
        assert metrics['min_rtt'] == 20.5
        assert metrics['max_rtt'] == 20.5
        assert metrics['avg_rtt'] == 20.5
        assert metrics['stddev_rtt'] == 0.0
        assert metrics['jitter'] == 0.0
    
    def test_calculate_metrics_multiple_results(self):
        """Test metrics calculation with multiple results."""
        ping_results = [
            {'rtt': 10.0, 'timestamp': 1234567890},
            {'rtt': 20.0, 'timestamp': 1234567891},
            {'rtt': 30.0, 'timestamp': 1234567892},
            {'rtt': 40.0, 'timestamp': 1234567893}
        ]
        metrics = self.plugin._calculate_metrics(ping_results)
        
        assert metrics['packets_sent'] == 4
        assert metrics['packets_received'] == 4
        assert metrics['packet_loss'] == 0.0
        assert metrics['min_rtt'] == 10.0
        assert metrics['max_rtt'] == 40.0
        assert metrics['avg_rtt'] == 25.0
        assert metrics['stddev_rtt'] > 0  # Should have some deviation
        assert metrics['jitter'] > 0  # Should have some jitter
    
    def test_parse_ping_output_linux(self):
        """Test parsing Linux ping output."""
        output = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=20.1 ms
64 bytes from 8.8.8.8: icmp_seq=2 ttl=118 time=19.8 ms
64 bytes from 8.8.8.8: icmp_seq=3 ttl=118 time=20.5 ms
64 bytes from 8.8.8.8: icmp_seq=4 ttl=118 time=19.9 ms

--- 8.8.8.8 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3004ms
rtt min/avg/max/mdev = 19.8/20.075/20.5/0.287 ms"""
        
        results = self.plugin._parse_ping_output(output, 'linux')
        
        assert len(results) == 4
        assert results[0]['rtt'] == 20.1
        assert results[1]['rtt'] == 19.8
        assert results[2]['rtt'] == 20.5
        assert results[3]['rtt'] == 19.9
    
    def test_parse_ping_output_windows(self):
        """Test parsing Windows ping output."""
        output = """Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=20ms TTL=118
Reply from 8.8.8.8: bytes=32 time=19ms TTL=118
Reply from 8.8.8.8: bytes=32 time=21ms TTL=118
Reply from 8.8.8.8: bytes=32 time=20ms TTL=118

Ping statistics for 8.8.8.8:
    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 19ms, Maximum = 21ms, Average = 20ms"""
        
        results = self.plugin._parse_ping_output(output, 'windows')
        
        assert len(results) == 4
        assert results[0]['rtt'] == 20.0
        assert results[1]['rtt'] == 19.0
        assert results[2]['rtt'] == 21.0
        assert results[3]['rtt'] == 20.0
    
    def test_parse_ping_output_empty(self):
        """Test parsing empty ping output."""
        results = self.plugin._parse_ping_output('', 'linux')
        assert results == []
    
    def test_parse_ping_output_no_replies(self):
        """Test parsing ping output with no replies."""
        output = """PING 192.168.1.999 (192.168.1.999) 56(84) bytes of data.

--- 192.168.1.999 ping statistics ---
4 packets transmitted, 0 received, 100% packet loss, time 3000ms"""
        
        results = self.plugin._parse_ping_output(output, 'linux')
        assert results == []
    
    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_ping_success(self, mock_subprocess):
        """Test successful ping execution."""
        # Mock subprocess
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            b'64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=20.1 ms\n'
            b'64 bytes from 8.8.8.8: icmp_seq=2 ttl=118 time=19.8 ms\n',
            b''
        )
        mock_subprocess.return_value = mock_process
        
        results = await self.plugin._ping(
            target='8.8.8.8',
            count=2,
            interval=1.0,
            packet_size=32,
            ttl=64,
            timeout=5.0
        )
        
        assert len(results) == 2
        assert results[0]['rtt'] == 20.1
        assert results[1]['rtt'] == 19.8
    
    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_ping_command_failure(self, mock_subprocess):
        """Test ping command failure."""
        # Mock subprocess failure
        mock_process = AsyncMock()
        mock_process.returncode = 2  # Command error
        mock_process.communicate.return_value = (b'', b'ping: unknown host')
        mock_subprocess.return_value = mock_process
        
        with pytest.raises(ProtocolError, match="Ping command failed"):
            await self.plugin._ping(
                target='invalid.host',
                count=1,
                interval=1.0,
                packet_size=32,
                ttl=64,
                timeout=5.0
            )
    
    @pytest.mark.asyncio
    @patch('asyncio.create_subprocess_exec')
    async def test_ping_timeout(self, mock_subprocess):
        """Test ping command timeout."""
        # Mock subprocess that times out
        mock_process = AsyncMock()
        mock_process.communicate.side_effect = asyncio.TimeoutError()
        mock_subprocess.return_value = mock_process
        
        with pytest.raises(ProtocolError, match="Ping command timed out"):
            await self.plugin._ping(
                target='8.8.8.8',
                count=1,
                interval=1.0,
                packet_size=32,
                ttl=64,
                timeout=1.0
            )
    
    @pytest.mark.asyncio
    @patch.object(ICMPPlugin, '_ping')
    async def test_execute_success(self, mock_ping):
        """Test successful ICMP test execution."""
        # Mock ping results
        mock_ping.return_value = [
            {'rtt': 20.0, 'timestamp': 1234567890},
            {'rtt': 21.0, 'timestamp': 1234567891},
            {'rtt': 19.0, 'timestamp': 1234567892},
            {'rtt': 20.5, 'timestamp': 1234567893}
        ]
        
        config = ProtocolConfig(
            target='8.8.8.8',
            timeout=5.0,
            parameters={'count': 4}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'icmp'
        assert result.target == '8.8.8.8'
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.error_message is None
        assert result.metrics['packets_received'] == 4
        assert result.metrics['packet_loss'] == 0.0
        assert result.metrics['avg_rtt'] == 20.12  # Rounded to 2 decimal places
        assert 'ping_results' in result.raw_data
    
    @pytest.mark.asyncio
    @patch.object(ICMPPlugin, '_ping')
    async def test_execute_high_packet_loss(self, mock_ping):
        """Test ICMP test execution with high packet loss."""
        # Mock ping results with only 1 out of 4 packets received
        mock_ping.return_value = [
            {'rtt': 20.0, 'timestamp': 1234567890}
        ]
        
        config = ProtocolConfig(
            target='8.8.8.8',
            timeout=5.0,
            parameters={'count': 4}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'icmp'
        assert result.status == ProtocolTestStatus.ERROR
        assert "High packet loss" in result.error_message
        assert result.metrics['packet_loss'] == 75.0
    
    @pytest.mark.asyncio
    @patch.object(ICMPPlugin, '_ping')
    async def test_execute_total_packet_loss(self, mock_ping):
        """Test ICMP test execution with total packet loss."""
        # Mock ping results with no packets received
        mock_ping.return_value = []
        
        config = ProtocolConfig(
            target='8.8.8.8',
            timeout=5.0,
            parameters={'count': 4}
        )
        
        result = await self.plugin.execute(config)
        
        assert result.protocol == 'icmp'
        assert result.status == ProtocolTestStatus.FAILED
        assert result.error_message == "All packets lost"
        assert result.metrics['packet_loss'] == 100.0
    
    @pytest.mark.asyncio
    async def test_execute_invalid_config(self):
        """Test ICMP test execution with invalid configuration."""
        config = ProtocolConfig(target='')  # Invalid target
        
        with pytest.raises(ProtocolError, match="Invalid configuration"):
            await self.plugin.execute(config)
    
    @pytest.mark.asyncio
    @patch.object(ICMPPlugin, '_ping')
    async def test_execute_ping_exception(self, mock_ping):
        """Test ICMP test execution when ping raises exception."""
        mock_ping.side_effect = Exception("Network error")
        
        config = ProtocolConfig(target='8.8.8.8')
        
        with pytest.raises(ProtocolError, match="ICMP test failed"):
            await self.plugin.execute(config)
    
    @pytest.mark.asyncio
    @patch.object(ICMPPlugin, '_ping')
    async def test_execute_custom_parameters(self, mock_ping):
        """Test ICMP test execution with custom parameters."""
        mock_ping.return_value = [
            {'rtt': 15.0, 'timestamp': 1234567890},
            {'rtt': 16.0, 'timestamp': 1234567891}
        ]
        
        config = ProtocolConfig(
            target='example.com',
            timeout=10.0,
            parameters={
                'count': 2,
                'interval': 0.5,
                'packet_size': 64,
                'ttl': 32
            }
        )
        
        result = await self.plugin.execute(config)
        
        # Verify ping was called with correct parameters
        mock_ping.assert_called_once_with(
            target='example.com',
            count=2,
            interval=0.5,
            packet_size=64,
            ttl=32,
            timeout=10.0
        )
        
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.raw_data['parameters']['count'] == 2
        assert result.raw_data['parameters']['interval'] == 0.5
        assert result.raw_data['parameters']['packet_size'] == 64
        assert result.raw_data['parameters']['ttl'] == 32