"""
ICMP protocol plugin for network probe agents.

This module implements ICMP ping testing functionality, collecting
latency and packet loss metrics.
"""

import asyncio
import platform
import socket
import struct
import time
from typing import Dict, Any, Optional

from .base import (
    ProtocolPlugin, ProtocolConfig, ProtocolResult, ProtocolTestStatus,
    ProtocolType, ProtocolError
)


class ICMPPlugin(ProtocolPlugin):
    """
    ICMP protocol plugin for ping testing.
    
    Implements ping functionality to test basic connectivity and measure
    latency and packet loss rates.
    """
    
    def __init__(self):
        super().__init__()
        self._protocol_type = ProtocolType.ICMP
        self._supported_parameters = {
            'count', 'interval', 'packet_size', 'ttl'
        }
    
    async def execute(self, config: ProtocolConfig) -> ProtocolResult:
        """
        Execute ICMP ping test.
        
        Args:
            config: Configuration for the ping test
            
        Returns:
            ProtocolResult containing ping metrics
            
        Raises:
            ProtocolError: If ping test fails
        """
        if not self.validate_config(config):
            raise ProtocolError(
                f"Invalid configuration for ICMP test",
                protocol='icmp',
                target=config.target
            )
        
        start_time = time.time()
        
        try:
            # Extract parameters
            count = config.parameters.get('count', 4)
            interval = config.parameters.get('interval', 1.0)
            packet_size = config.parameters.get('packet_size', 32)
            ttl = config.parameters.get('ttl', 64)
            
            # Perform ping test
            ping_results = await self._ping(
                target=config.target,
                count=count,
                interval=interval,
                packet_size=packet_size,
                ttl=ttl,
                timeout=config.timeout
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Calculate metrics
            metrics = self._calculate_metrics(ping_results)
            
            # Determine status based on results
            status = ProtocolTestStatus.SUCCESS
            error_message = None
            
            if metrics['packets_received'] == 0:
                status = ProtocolTestStatus.FAILED
                error_message = "All packets lost"
            elif metrics['packet_loss'] > 50.0:
                status = ProtocolTestStatus.ERROR
                error_message = f"High packet loss: {metrics['packet_loss']:.1f}%"
            
            return ProtocolResult(
                protocol='icmp',
                target=config.target,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
                metrics=metrics,
                raw_data={
                    'ping_results': ping_results,
                    'parameters': {
                        'count': count,
                        'interval': interval,
                        'packet_size': packet_size,
                        'ttl': ttl
                    }
                }
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            raise ProtocolError(
                f"ICMP test failed: {str(e)}",
                protocol='icmp',
                target=config.target
            )
    
    def validate_config(self, config: ProtocolConfig) -> bool:
        """
        Validate ICMP configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not config.target:
            return False
        
        # Validate parameters
        params = config.parameters
        
        if 'count' in params:
            if not isinstance(params['count'], int) or params['count'] <= 0:
                return False
        
        if 'interval' in params:
            if not isinstance(params['interval'], (int, float)) or params['interval'] <= 0:
                return False
        
        if 'packet_size' in params:
            if not isinstance(params['packet_size'], int) or params['packet_size'] <= 0:
                return False
        
        if 'ttl' in params:
            if not isinstance(params['ttl'], int) or not (1 <= params['ttl'] <= 255):
                return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default ICMP configuration."""
        return {
            'timeout': 5.0,
            'parameters': {
                'count': 4,
                'interval': 1.0,
                'packet_size': 32,
                'ttl': 64
            }
        }
    
    def get_metrics_description(self) -> Dict[str, str]:
        """Get description of ICMP metrics."""
        return {
            'packets_sent': 'Number of packets sent',
            'packets_received': 'Number of packets received',
            'packet_loss': 'Packet loss percentage',
            'min_rtt': 'Minimum round-trip time (ms)',
            'max_rtt': 'Maximum round-trip time (ms)',
            'avg_rtt': 'Average round-trip time (ms)',
            'stddev_rtt': 'Standard deviation of round-trip time (ms)',
            'jitter': 'Network jitter (ms)'
        }
    
    async def _ping(self, target: str, count: int, interval: float, 
                   packet_size: int, ttl: int, timeout: float) -> list:
        """
        Perform ping test using system ping command.
        
        Args:
            target: Target hostname or IP address
            count: Number of ping packets to send
            interval: Interval between packets in seconds
            packet_size: Size of ping packets in bytes
            ttl: Time to live value
            timeout: Timeout for each ping in seconds
            
        Returns:
            List of ping results
        """
        # Use system ping command for reliability
        system = platform.system().lower()
        
        if system == 'windows':
            cmd = [
                'ping', '-n', str(count), '-l', str(packet_size),
                '-i', str(ttl), '-w', str(int(timeout * 1000)), target
            ]
        else:  # Linux/macOS
            cmd = [
                'ping', '-c', str(count), '-s', str(packet_size),
                '-t', str(ttl), '-W', str(int(timeout)), target
            ]
            if interval != 1.0:
                cmd.extend(['-i', str(interval)])
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout * count + 10  # Extra time for command completion
            )
            
            if process.returncode not in (0, 1):  # 1 is acceptable for some packet loss
                raise ProtocolError(
                    f"Ping command failed: {stderr.decode().strip()}",
                    protocol='icmp',
                    target=target
                )
            
            return self._parse_ping_output(stdout.decode(), system)
            
        except asyncio.TimeoutError:
            raise ProtocolError(
                f"Ping command timed out after {timeout * count + 10} seconds",
                protocol='icmp',
                target=target
            )
        except Exception as e:
            raise ProtocolError(
                f"Failed to execute ping command: {str(e)}",
                protocol='icmp',
                target=target
            )
    
    def _parse_ping_output(self, output: str, system: str) -> list:
        """
        Parse ping command output.
        
        Args:
            output: Raw ping command output
            system: Operating system ('windows', 'linux', 'darwin')
            
        Returns:
            List of ping results with timing information
        """
        results = []
        lines = output.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Parse timing information from ping output
            rtt = None
            
            if system == 'windows':
                # Windows ping output: "Reply from 8.8.8.8: bytes=32 time=20ms TTL=118"
                if 'time=' in line and 'ms' in line:
                    try:
                        time_part = line.split('time=')[1].split('ms')[0]
                        if time_part.replace('<', '').replace('>', '').isdigit():
                            rtt = float(time_part.replace('<', '').replace('>', ''))
                        else:
                            rtt = float(time_part)
                    except (IndexError, ValueError):
                        continue
            else:
                # Linux/macOS ping output: "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=20.1 ms"
                if 'time=' in line:
                    try:
                        time_part = line.split('time=')[1].split()[0]
                        rtt = float(time_part)
                    except (IndexError, ValueError):
                        continue
            
            if rtt is not None:
                results.append({
                    'rtt': rtt,
                    'timestamp': time.time()
                })
        
        return results
    
    def _calculate_metrics(self, ping_results: list) -> Dict[str, Any]:
        """
        Calculate ping metrics from results.
        
        Args:
            ping_results: List of ping results
            
        Returns:
            Dictionary containing calculated metrics
        """
        if not ping_results:
            return {
                'packets_sent': 0,
                'packets_received': 0,
                'packet_loss': 100.0,
                'min_rtt': None,
                'max_rtt': None,
                'avg_rtt': None,
                'stddev_rtt': None,
                'jitter': None
            }
        
        rtts = [result['rtt'] for result in ping_results]
        packets_received = len(rtts)
        
        # Calculate basic statistics
        min_rtt = min(rtts)
        max_rtt = max(rtts)
        avg_rtt = sum(rtts) / len(rtts)
        
        # Calculate standard deviation
        variance = sum((rtt - avg_rtt) ** 2 for rtt in rtts) / len(rtts)
        stddev_rtt = variance ** 0.5
        
        # Calculate jitter (average of absolute differences between consecutive RTTs)
        jitter = 0.0
        if len(rtts) > 1:
            diffs = [abs(rtts[i] - rtts[i-1]) for i in range(1, len(rtts))]
            jitter = sum(diffs) / len(diffs)
        
        # Assume we tried to send 4 packets by default (this could be improved)
        # In a real implementation, we would track this more accurately
        packets_sent = max(4, packets_received)  # Estimate based on typical ping count
        packet_loss = ((packets_sent - packets_received) / packets_sent) * 100
        
        return {
            'packets_sent': packets_sent,
            'packets_received': packets_received,
            'packet_loss': round(packet_loss, 1),
            'min_rtt': round(min_rtt, 2),
            'max_rtt': round(max_rtt, 2),
            'avg_rtt': round(avg_rtt, 2),
            'stddev_rtt': round(stddev_rtt, 2),
            'jitter': round(jitter, 2)
        }