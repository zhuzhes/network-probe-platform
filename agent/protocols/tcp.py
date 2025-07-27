"""
TCP protocol plugin for network probe agents.

This module implements TCP connection testing functionality, collecting
connection time and availability metrics.
"""

import asyncio
import socket
import time
from typing import Dict, Any, Optional

from .base import (
    ProtocolPlugin, ProtocolConfig, ProtocolResult, ProtocolTestStatus,
    ProtocolType, ProtocolError
)


class TCPPlugin(ProtocolPlugin):
    """
    TCP protocol plugin for connection testing.
    
    Implements TCP connection tests to measure connection establishment time,
    service availability, and connection reliability.
    """
    
    def __init__(self):
        super().__init__()
        self._protocol_type = ProtocolType.TCP
        self._supported_parameters = {
            'connect_attempts', 'retry_interval', 'source_port'
        }
    
    async def execute(self, config: ProtocolConfig) -> ProtocolResult:
        """
        Execute TCP connection test.
        
        Args:
            config: Configuration for the TCP test
            
        Returns:
            ProtocolResult containing TCP connection metrics
            
        Raises:
            ProtocolError: If TCP test fails
        """
        if not self.validate_config(config):
            raise ProtocolError(
                f"Invalid configuration for TCP test",
                protocol='tcp',
                target=config.target
            )
        
        start_time = time.time()
        
        try:
            # Extract parameters
            connect_attempts = config.parameters.get('connect_attempts', 3)
            retry_interval = config.parameters.get('retry_interval', 1.0)
            source_port = config.parameters.get('source_port', None)
            
            # Perform TCP connection tests
            connection_results = await self._test_tcp_connection(
                target=config.target,
                port=config.port or 80,
                timeout=config.timeout,
                attempts=connect_attempts,
                retry_interval=retry_interval,
                source_port=source_port
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Calculate metrics
            metrics = self._calculate_metrics(connection_results)
            
            # Determine status based on results
            status = ProtocolTestStatus.SUCCESS
            error_message = None
            
            if metrics['successful_connections'] == 0:
                status = ProtocolTestStatus.FAILED
                error_message = "All connection attempts failed"
            elif metrics['success_rate'] < 50.0:
                status = ProtocolTestStatus.ERROR
                error_message = f"Low success rate: {metrics['success_rate']:.1f}%"
            elif metrics['avg_connect_time'] > config.timeout * 1000 * 0.8:
                status = ProtocolTestStatus.ERROR
                error_message = f"High connection time: {metrics['avg_connect_time']:.1f}ms"
            
            return ProtocolResult(
                protocol='tcp',
                target=config.target,
                port=config.port or 80,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
                metrics=metrics,
                raw_data={
                    'connection_results': connection_results,
                    'parameters': {
                        'connect_attempts': connect_attempts,
                        'retry_interval': retry_interval,
                        'source_port': source_port
                    }
                }
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            raise ProtocolError(
                f"TCP test failed: {str(e)}",
                protocol='tcp',
                target=config.target
            )
    
    def validate_config(self, config: ProtocolConfig) -> bool:
        """
        Validate TCP configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not config.target:
            return False
        
        # Port is required for TCP
        if config.port is None:
            return False
        
        if not isinstance(config.port, int) or not (1 <= config.port <= 65535):
            return False
        
        # Validate parameters
        params = config.parameters
        
        if 'connect_attempts' in params:
            if not isinstance(params['connect_attempts'], int) or params['connect_attempts'] <= 0:
                return False
        
        if 'retry_interval' in params:
            if not isinstance(params['retry_interval'], (int, float)) or params['retry_interval'] < 0:
                return False
        
        if 'source_port' in params:
            if params['source_port'] is not None:
                if not isinstance(params['source_port'], int) or not (1 <= params['source_port'] <= 65535):
                    return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default TCP configuration."""
        return {
            'timeout': 5.0,
            'parameters': {
                'connect_attempts': 3,
                'retry_interval': 1.0,
                'source_port': None
            }
        }
    
    def get_metrics_description(self) -> Dict[str, str]:
        """Get description of TCP metrics."""
        return {
            'total_attempts': 'Total connection attempts made',
            'successful_connections': 'Number of successful connections',
            'failed_connections': 'Number of failed connections',
            'success_rate': 'Connection success rate percentage',
            'min_connect_time': 'Minimum connection time (ms)',
            'max_connect_time': 'Maximum connection time (ms)',
            'avg_connect_time': 'Average connection time (ms)',
            'stddev_connect_time': 'Standard deviation of connection time (ms)',
            'connection_reliability': 'Connection reliability score (0-100)'
        }
    
    async def _test_tcp_connection(self, target: str, port: int, timeout: float,
                                  attempts: int, retry_interval: float,
                                  source_port: Optional[int] = None) -> list:
        """
        Test TCP connection multiple times.
        
        Args:
            target: Target hostname or IP address
            port: Target port number
            timeout: Connection timeout in seconds
            attempts: Number of connection attempts
            retry_interval: Interval between attempts in seconds
            source_port: Source port to bind to (optional)
            
        Returns:
            List of connection test results
        """
        results = []
        
        for attempt in range(attempts):
            if attempt > 0:
                await asyncio.sleep(retry_interval)
            
            result = await self._single_tcp_connection(
                target, port, timeout, source_port
            )
            result['attempt'] = attempt + 1
            results.append(result)
        
        return results
    
    async def _single_tcp_connection(self, target: str, port: int, timeout: float,
                                   source_port: Optional[int] = None) -> Dict[str, Any]:
        """
        Perform a single TCP connection test.
        
        Args:
            target: Target hostname or IP address
            port: Target port number
            timeout: Connection timeout in seconds
            source_port: Source port to bind to (optional)
            
        Returns:
            Dictionary containing connection test result
        """
        start_time = time.time()
        
        try:
            # Resolve hostname to IP address
            try:
                resolved_ip = socket.gethostbyname(target)
            except socket.gaierror as e:
                return {
                    'success': False,
                    'connect_time': None,
                    'error': f"DNS resolution failed: {str(e)}",
                    'timestamp': start_time,
                    'resolved_ip': None
                }
            
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            try:
                # Bind to source port if specified
                if source_port:
                    sock.bind(('', source_port))
                
                # Attempt connection
                connect_start = time.time()
                sock.connect((resolved_ip, port))
                connect_time = (time.time() - connect_start) * 1000  # Convert to ms
                
                # Connection successful
                return {
                    'success': True,
                    'connect_time': round(connect_time, 2),
                    'error': None,
                    'timestamp': start_time,
                    'resolved_ip': resolved_ip
                }
                
            except socket.timeout:
                return {
                    'success': False,
                    'connect_time': None,
                    'error': f"Connection timeout after {timeout}s",
                    'timestamp': start_time,
                    'resolved_ip': resolved_ip
                }
            except socket.error as e:
                return {
                    'success': False,
                    'connect_time': None,
                    'error': f"Connection failed: {str(e)}",
                    'timestamp': start_time,
                    'resolved_ip': resolved_ip
                }
            finally:
                sock.close()
                
        except Exception as e:
            return {
                'success': False,
                'connect_time': None,
                'error': f"Unexpected error: {str(e)}",
                'timestamp': start_time,
                'resolved_ip': None
            }
    
    def _calculate_metrics(self, connection_results: list) -> Dict[str, Any]:
        """
        Calculate TCP connection metrics from results.
        
        Args:
            connection_results: List of connection test results
            
        Returns:
            Dictionary containing calculated metrics
        """
        if not connection_results:
            return {
                'total_attempts': 0,
                'successful_connections': 0,
                'failed_connections': 0,
                'success_rate': 0.0,
                'min_connect_time': None,
                'max_connect_time': None,
                'avg_connect_time': None,
                'stddev_connect_time': None,
                'connection_reliability': 0.0
            }
        
        total_attempts = len(connection_results)
        successful_connections = sum(1 for result in connection_results if result['success'])
        failed_connections = total_attempts - successful_connections
        success_rate = (successful_connections / total_attempts) * 100
        
        # Calculate connection time statistics for successful connections
        successful_times = [
            result['connect_time'] for result in connection_results 
            if result['success'] and result['connect_time'] is not None
        ]
        
        if successful_times:
            min_connect_time = min(successful_times)
            max_connect_time = max(successful_times)
            avg_connect_time = sum(successful_times) / len(successful_times)
            
            # Calculate standard deviation
            if len(successful_times) > 1:
                variance = sum((time - avg_connect_time) ** 2 for time in successful_times) / len(successful_times)
                stddev_connect_time = variance ** 0.5
            else:
                stddev_connect_time = 0.0
        else:
            min_connect_time = None
            max_connect_time = None
            avg_connect_time = None
            stddev_connect_time = None
        
        # Calculate connection reliability score
        # Based on success rate and connection time consistency
        reliability = success_rate
        if successful_times and len(successful_times) > 1:
            # Penalize high variance in connection times
            cv = (stddev_connect_time / avg_connect_time) if avg_connect_time > 0 else 0
            reliability = max(0, reliability - (cv * 10))  # Reduce score for high variance
        
        return {
            'total_attempts': total_attempts,
            'successful_connections': successful_connections,
            'failed_connections': failed_connections,
            'success_rate': round(success_rate, 1),
            'min_connect_time': round(min_connect_time, 2) if min_connect_time is not None else None,
            'max_connect_time': round(max_connect_time, 2) if max_connect_time is not None else None,
            'avg_connect_time': round(avg_connect_time, 2) if avg_connect_time is not None else None,
            'stddev_connect_time': round(stddev_connect_time, 2) if stddev_connect_time is not None else None,
            'connection_reliability': round(reliability, 1)
        }