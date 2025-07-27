"""
UDP protocol plugin for network probe agents.

This module implements UDP packet testing functionality, collecting
transmission reliability and response time metrics.
"""

import asyncio
import socket
import struct
import time
import random
from typing import Dict, Any, Optional

from .base import (
    ProtocolPlugin, ProtocolConfig, ProtocolResult, ProtocolTestStatus,
    ProtocolType, ProtocolError
)


class UDPPlugin(ProtocolPlugin):
    """
    UDP protocol plugin for packet transmission testing.
    
    Implements UDP packet tests to measure transmission reliability,
    response times, and packet loss rates.
    """
    
    def __init__(self):
        super().__init__()
        self._protocol_type = ProtocolType.UDP
        self._supported_parameters = {
            'packet_count', 'packet_size', 'interval', 'expect_response'
        }
    
    async def execute(self, config: ProtocolConfig) -> ProtocolResult:
        """
        Execute UDP packet test.
        
        Args:
            config: Configuration for the UDP test
            
        Returns:
            ProtocolResult containing UDP transmission metrics
            
        Raises:
            ProtocolError: If UDP test fails
        """
        if not self.validate_config(config):
            raise ProtocolError(
                f"Invalid configuration for UDP test",
                protocol='udp',
                target=config.target
            )
        
        start_time = time.time()
        
        try:
            # Extract parameters
            packet_count = config.parameters.get('packet_count', 5)
            packet_size = config.parameters.get('packet_size', 64)
            interval = config.parameters.get('interval', 1.0)
            expect_response = config.parameters.get('expect_response', False)
            
            # Perform UDP packet tests
            packet_results = await self._test_udp_packets(
                target=config.target,
                port=config.port or 53,  # Default to DNS port
                packet_count=packet_count,
                packet_size=packet_size,
                interval=interval,
                timeout=config.timeout,
                expect_response=expect_response
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Calculate metrics
            metrics = self._calculate_metrics(packet_results, expect_response)
            
            # Determine status based on results
            status = ProtocolTestStatus.SUCCESS
            error_message = None
            
            if metrics['packets_sent'] == 0:
                status = ProtocolTestStatus.ERROR
                error_message = "No packets could be sent"
            elif expect_response and metrics['response_rate'] == 0.0:
                status = ProtocolTestStatus.FAILED
                error_message = "No responses received"
            elif expect_response and metrics['response_rate'] < 50.0:
                status = ProtocolTestStatus.ERROR
                error_message = f"Low response rate: {metrics['response_rate']:.1f}%"
            elif metrics['transmission_errors'] > metrics['packets_sent'] * 0.5:
                status = ProtocolTestStatus.ERROR
                error_message = f"High transmission error rate: {metrics['error_rate']:.1f}%"
            
            return ProtocolResult(
                protocol='udp',
                target=config.target,
                port=config.port or 53,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
                metrics=metrics,
                raw_data={
                    'packet_results': packet_results,
                    'parameters': {
                        'packet_count': packet_count,
                        'packet_size': packet_size,
                        'interval': interval,
                        'expect_response': expect_response
                    }
                }
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            raise ProtocolError(
                f"UDP test failed: {str(e)}",
                protocol='udp',
                target=config.target
            )
    
    def validate_config(self, config: ProtocolConfig) -> bool:
        """
        Validate UDP configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not config.target:
            return False
        
        # Port is required for UDP
        if config.port is None:
            return False
        
        if not isinstance(config.port, int) or not (1 <= config.port <= 65535):
            return False
        
        # Validate parameters
        params = config.parameters
        
        if 'packet_count' in params:
            if not isinstance(params['packet_count'], int) or params['packet_count'] <= 0:
                return False
        
        if 'packet_size' in params:
            if not isinstance(params['packet_size'], int) or params['packet_size'] <= 0:
                return False
        
        if 'interval' in params:
            if not isinstance(params['interval'], (int, float)) or params['interval'] < 0:
                return False
        
        if 'expect_response' in params:
            if not isinstance(params['expect_response'], bool):
                return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default UDP configuration."""
        return {
            'timeout': 5.0,
            'parameters': {
                'packet_count': 5,
                'packet_size': 64,
                'interval': 1.0,
                'expect_response': False
            }
        }
    
    def get_metrics_description(self) -> Dict[str, str]:
        """Get description of UDP metrics."""
        return {
            'packets_sent': 'Number of packets sent',
            'packets_received': 'Number of response packets received',
            'transmission_errors': 'Number of transmission errors',
            'response_rate': 'Response rate percentage (if expecting responses)',
            'error_rate': 'Transmission error rate percentage',
            'min_response_time': 'Minimum response time (ms)',
            'max_response_time': 'Maximum response time (ms)',
            'avg_response_time': 'Average response time (ms)',
            'stddev_response_time': 'Standard deviation of response time (ms)',
            'jitter': 'Response time jitter (ms)',
            'transmission_reliability': 'Overall transmission reliability score (0-100)'
        }
    
    async def _test_udp_packets(self, target: str, port: int, packet_count: int,
                               packet_size: int, interval: float, timeout: float,
                               expect_response: bool) -> list:
        """
        Test UDP packet transmission.
        
        Args:
            target: Target hostname or IP address
            port: Target port number
            packet_count: Number of packets to send
            packet_size: Size of each packet in bytes
            interval: Interval between packets in seconds
            timeout: Response timeout in seconds
            expect_response: Whether to expect responses
            
        Returns:
            List of packet transmission results
        """
        results = []
        
        # Resolve hostname to IP address
        try:
            resolved_ip = socket.gethostbyname(target)
        except socket.gaierror as e:
            raise ProtocolError(
                f"DNS resolution failed: {str(e)}",
                protocol='udp',
                target=target
            )
        
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        
        try:
            for i in range(packet_count):
                if i > 0:
                    await asyncio.sleep(interval)
                
                result = await self._send_udp_packet(
                    sock, resolved_ip, port, packet_size, i + 1, timeout, expect_response
                )
                results.append(result)
                
        finally:
            sock.close()
        
        return results
    
    async def _send_udp_packet(self, sock: socket.socket, target_ip: str, port: int,
                              packet_size: int, sequence: int, timeout: float,
                              expect_response: bool) -> Dict[str, Any]:
        """
        Send a single UDP packet and optionally wait for response.
        
        Args:
            sock: UDP socket to use
            target_ip: Target IP address
            port: Target port number
            packet_size: Size of packet to send
            sequence: Packet sequence number
            timeout: Response timeout in seconds
            expect_response: Whether to expect a response
            
        Returns:
            Dictionary containing packet transmission result
        """
        start_time = time.time()
        
        try:
            # Create packet data with sequence number and random payload
            packet_data = self._create_packet_data(packet_size, sequence)
            
            # Send packet
            send_time = time.time()
            sock.sendto(packet_data, (target_ip, port))
            
            result = {
                'sequence': sequence,
                'sent': True,
                'send_time': send_time,
                'packet_size': len(packet_data),
                'transmission_error': None
            }
            
            if expect_response:
                # Wait for response
                try:
                    response_data, addr = sock.recvfrom(4096)
                    response_time = time.time()
                    response_duration = (response_time - send_time) * 1000  # Convert to ms
                    
                    result.update({
                        'response_received': True,
                        'response_time': round(response_duration, 2),
                        'response_size': len(response_data),
                        'response_from': addr[0]
                    })
                    
                except socket.timeout:
                    result.update({
                        'response_received': False,
                        'response_time': None,
                        'timeout': True
                    })
                    
                except socket.error as e:
                    result.update({
                        'response_received': False,
                        'response_time': None,
                        'response_error': str(e)
                    })
            else:
                result.update({
                    'response_received': None,
                    'response_time': None
                })
            
            return result
            
        except socket.error as e:
            return {
                'sequence': sequence,
                'sent': False,
                'send_time': start_time,
                'packet_size': packet_size,
                'transmission_error': str(e),
                'response_received': None,
                'response_time': None
            }
    
    def _create_packet_data(self, size: int, sequence: int) -> bytes:
        """
        Create UDP packet data with sequence number and payload.
        
        Args:
            size: Desired packet size in bytes
            sequence: Packet sequence number
            
        Returns:
            Packet data as bytes
        """
        # Create header with sequence number (4 bytes) and timestamp (8 bytes)
        header = struct.pack('!IQ', sequence, int(time.time() * 1000000))
        
        # Calculate remaining payload size
        payload_size = max(0, size - len(header))
        
        # Create random payload
        payload = bytes([random.randint(0, 255) for _ in range(payload_size)])
        
        return header + payload
    
    def _calculate_metrics(self, packet_results: list, expect_response: bool) -> Dict[str, Any]:
        """
        Calculate UDP transmission metrics from results.
        
        Args:
            packet_results: List of packet transmission results
            expect_response: Whether responses were expected
            
        Returns:
            Dictionary containing calculated metrics
        """
        if not packet_results:
            return {
                'packets_sent': 0,
                'packets_received': 0,
                'transmission_errors': 0,
                'response_rate': 0.0,
                'error_rate': 0.0,
                'min_response_time': None,
                'max_response_time': None,
                'avg_response_time': None,
                'stddev_response_time': None,
                'jitter': None,
                'transmission_reliability': 0.0
            }
        
        total_packets = len(packet_results)
        packets_sent = sum(1 for result in packet_results if result['sent'])
        transmission_errors = sum(1 for result in packet_results if not result['sent'])
        
        # Calculate response metrics if responses were expected
        if expect_response:
            packets_received = sum(
                1 for result in packet_results 
                if result.get('response_received') is True
            )
            response_rate = (packets_received / packets_sent) * 100 if packets_sent > 0 else 0.0
            
            # Calculate response time statistics
            response_times = [
                result['response_time'] for result in packet_results
                if result.get('response_time') is not None
            ]
            
            if response_times:
                min_response_time = min(response_times)
                max_response_time = max(response_times)
                avg_response_time = sum(response_times) / len(response_times)
                
                # Calculate standard deviation
                if len(response_times) > 1:
                    variance = sum((time - avg_response_time) ** 2 for time in response_times) / len(response_times)
                    stddev_response_time = variance ** 0.5
                    
                    # Calculate jitter (average of absolute differences between consecutive response times)
                    diffs = [abs(response_times[i] - response_times[i-1]) for i in range(1, len(response_times))]
                    jitter = sum(diffs) / len(diffs) if diffs else 0.0
                else:
                    stddev_response_time = 0.0
                    jitter = 0.0
            else:
                min_response_time = None
                max_response_time = None
                avg_response_time = None
                stddev_response_time = None
                jitter = None
        else:
            packets_received = 0
            response_rate = 0.0
            min_response_time = None
            max_response_time = None
            avg_response_time = None
            stddev_response_time = None
            jitter = None
        
        # Calculate error rate
        error_rate = (transmission_errors / total_packets) * 100 if total_packets > 0 else 0.0
        
        # Calculate transmission reliability score
        reliability = 100.0 - error_rate
        if expect_response:
            # Factor in response rate for reliability
            reliability = (reliability + response_rate) / 2
        
        return {
            'packets_sent': packets_sent,
            'packets_received': packets_received,
            'transmission_errors': transmission_errors,
            'response_rate': round(response_rate, 1),
            'error_rate': round(error_rate, 1),
            'min_response_time': round(min_response_time, 2) if min_response_time is not None else None,
            'max_response_time': round(max_response_time, 2) if max_response_time is not None else None,
            'avg_response_time': round(avg_response_time, 2) if avg_response_time is not None else None,
            'stddev_response_time': round(stddev_response_time, 2) if stddev_response_time is not None else None,
            'jitter': round(jitter, 2) if jitter is not None else None,
            'transmission_reliability': round(reliability, 1)
        }