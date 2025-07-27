"""
HTTP/HTTPS protocol plugin for network probe agents.

This module implements HTTP/HTTPS web service testing functionality, collecting
response time, status codes, and other web service metrics.
"""

import asyncio
import aiohttp
import ssl
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, urljoin

from .base import (
    ProtocolPlugin, ProtocolConfig, ProtocolResult, ProtocolTestStatus,
    ProtocolType, ProtocolError
)


class HTTPPlugin(ProtocolPlugin):
    """
    HTTP/HTTPS protocol plugin for web service testing.
    
    Implements HTTP/HTTPS requests to measure response time, status codes,
    content validation, and other web service metrics.
    """
    
    def __init__(self):
        super().__init__()
        self._protocol_type = ProtocolType.HTTP
        self._supported_parameters = {
            'method', 'headers', 'body', 'follow_redirects', 'verify_ssl',
            'user_agent', 'auth', 'cookies', 'content_check', 'status_codes',
            'max_redirects', 'request_attempts', 'retry_interval'
        }
    
    async def execute(self, config: ProtocolConfig) -> ProtocolResult:
        """
        Execute HTTP/HTTPS test.
        
        Args:
            config: Configuration for the HTTP test
            
        Returns:
            ProtocolResult containing HTTP response metrics
            
        Raises:
            ProtocolError: If HTTP test fails
        """
        if not self.validate_config(config):
            raise ProtocolError(
                f"Invalid configuration for HTTP test",
                protocol='http',
                target=config.target
            )
        
        start_time = time.time()
        
        try:
            # Build URL
            url = self._build_url(config.target, config.port)
            
            # Extract parameters
            method = config.parameters.get('method', 'GET').upper()
            headers = config.parameters.get('headers', {})
            body = config.parameters.get('body', None)
            follow_redirects = config.parameters.get('follow_redirects', True)
            verify_ssl = config.parameters.get('verify_ssl', True)
            user_agent = config.parameters.get('user_agent', 'NetworkProbe/1.0')
            auth = config.parameters.get('auth', None)
            cookies = config.parameters.get('cookies', {})
            content_check = config.parameters.get('content_check', None)
            expected_status_codes = config.parameters.get('status_codes', [200])
            max_redirects = config.parameters.get('max_redirects', 10)
            request_attempts = config.parameters.get('request_attempts', 3)
            retry_interval = config.parameters.get('retry_interval', 1.0)
            
            # Perform HTTP requests
            request_results = await self._test_http_requests(
                url=url,
                method=method,
                headers=headers,
                body=body,
                timeout=config.timeout,
                follow_redirects=follow_redirects,
                verify_ssl=verify_ssl,
                user_agent=user_agent,
                auth=auth,
                cookies=cookies,
                max_redirects=max_redirects,
                attempts=request_attempts,
                retry_interval=retry_interval
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Calculate metrics
            metrics = self._calculate_metrics(request_results)
            
            # Determine status based on results
            status, error_message = self._determine_status(
                request_results, expected_status_codes, content_check
            )
            
            return ProtocolResult(
                protocol='http' if not url.startswith('https') else 'https',
                target=config.target,
                port=config.port,
                status=status,
                duration_ms=duration_ms,
                error_message=error_message,
                metrics=metrics,
                raw_data={
                    'url': url,
                    'request_results': request_results,
                    'parameters': {
                        'method': method,
                        'headers': headers,
                        'body': body,
                        'follow_redirects': follow_redirects,
                        'verify_ssl': verify_ssl,
                        'user_agent': user_agent,
                        'auth': auth,
                        'cookies': cookies,
                        'content_check': content_check,
                        'expected_status_codes': expected_status_codes,
                        'max_redirects': max_redirects,
                        'request_attempts': request_attempts,
                        'retry_interval': retry_interval
                    }
                }
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            raise ProtocolError(
                f"HTTP test failed: {str(e)}",
                protocol='http',
                target=config.target
            )
    
    def validate_config(self, config: ProtocolConfig) -> bool:
        """
        Validate HTTP configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not config.target:
            return False
        
        # Validate URL format
        if not self._is_valid_url(config.target):
            return False
        
        # Validate parameters
        params = config.parameters
        
        if 'method' in params:
            if not isinstance(params['method'], str) or params['method'].upper() not in [
                'GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH'
            ]:
                return False
        
        if 'headers' in params:
            if not isinstance(params['headers'], dict):
                return False
        
        if 'follow_redirects' in params:
            if not isinstance(params['follow_redirects'], bool):
                return False
        
        if 'verify_ssl' in params:
            if not isinstance(params['verify_ssl'], bool):
                return False
        
        if 'status_codes' in params:
            if not isinstance(params['status_codes'], list):
                return False
            if not all(isinstance(code, int) and 100 <= code <= 599 for code in params['status_codes']):
                return False
        
        if 'max_redirects' in params:
            if not isinstance(params['max_redirects'], int) or params['max_redirects'] < 0:
                return False
        
        if 'request_attempts' in params:
            if not isinstance(params['request_attempts'], int) or params['request_attempts'] <= 0:
                return False
        
        if 'retry_interval' in params:
            if not isinstance(params['retry_interval'], (int, float)) or params['retry_interval'] < 0:
                return False
        
        return True
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default HTTP configuration."""
        return {
            'timeout': 10.0,
            'parameters': {
                'method': 'GET',
                'headers': {},
                'body': None,
                'follow_redirects': True,
                'verify_ssl': True,
                'user_agent': 'NetworkProbe/1.0',
                'auth': None,
                'cookies': {},
                'content_check': None,
                'status_codes': [200],
                'max_redirects': 10,
                'request_attempts': 3,
                'retry_interval': 1.0
            }
        }
    
    def get_metrics_description(self) -> Dict[str, str]:
        """Get description of HTTP metrics."""
        return {
            'total_requests': 'Total HTTP requests made',
            'successful_requests': 'Number of successful requests',
            'failed_requests': 'Number of failed requests',
            'success_rate': 'Request success rate percentage',
            'min_response_time': 'Minimum response time (ms)',
            'max_response_time': 'Maximum response time (ms)',
            'avg_response_time': 'Average response time (ms)',
            'stddev_response_time': 'Standard deviation of response time (ms)',
            'status_code_distribution': 'Distribution of HTTP status codes',
            'content_length_avg': 'Average response content length (bytes)',
            'redirect_count_avg': 'Average number of redirects',
            'ssl_handshake_time_avg': 'Average SSL handshake time (ms)',
            'dns_lookup_time_avg': 'Average DNS lookup time (ms)',
            'connect_time_avg': 'Average connection time (ms)',
            'first_byte_time_avg': 'Average time to first byte (ms)',
            'availability_score': 'Service availability score (0-100)'
        }
    
    def _build_url(self, target: str, port: Optional[int] = None) -> str:
        """
        Build complete URL from target and port.
        
        Args:
            target: Target URL or hostname
            port: Port number (optional)
            
        Returns:
            Complete URL string
        """
        if target.startswith(('http://', 'https://')):
            parsed = urlparse(target)
            if port and not parsed.port:
                # Add port to URL if not already present
                netloc = f"{parsed.hostname}:{port}"
                return f"{parsed.scheme}://{netloc}{parsed.path}"
            return target
        else:
            # Assume HTTP if no scheme provided
            scheme = 'https' if port == 443 else 'http'
            if port and port not in (80, 443):
                return f"{scheme}://{target}:{port}"
            return f"{scheme}://{target}"
    
    def _is_valid_url(self, url: str) -> bool:
        """
        Validate URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if url.startswith(('http://', 'https://')):
                parsed = urlparse(url)
                return bool(parsed.netloc)
            else:
                # Allow hostname/IP without scheme
                return bool(url.strip())
        except Exception:
            return False
    
    async def _test_http_requests(self, url: str, method: str, headers: Dict[str, str],
                                 body: Optional[str], timeout: float, follow_redirects: bool,
                                 verify_ssl: bool, user_agent: str, auth: Optional[Dict],
                                 cookies: Dict[str, str], max_redirects: int,
                                 attempts: int, retry_interval: float) -> List[Dict[str, Any]]:
        """
        Test HTTP requests multiple times.
        
        Args:
            url: Target URL
            method: HTTP method
            headers: Request headers
            body: Request body
            timeout: Request timeout
            follow_redirects: Whether to follow redirects
            verify_ssl: Whether to verify SSL certificates
            user_agent: User agent string
            auth: Authentication configuration
            cookies: Request cookies
            max_redirects: Maximum number of redirects
            attempts: Number of request attempts
            retry_interval: Interval between attempts
            
        Returns:
            List of request test results
        """
        results = []
        
        for attempt in range(attempts):
            if attempt > 0:
                await asyncio.sleep(retry_interval)
            
            result = await self._single_http_request(
                url, method, headers, body, timeout, follow_redirects,
                verify_ssl, user_agent, auth, cookies, max_redirects
            )
            result['attempt'] = attempt + 1
            results.append(result)
        
        return results
    
    async def _single_http_request(self, url: str, method: str, headers: Dict[str, str],
                                  body: Optional[str], timeout: float, follow_redirects: bool,
                                  verify_ssl: bool, user_agent: str, auth: Optional[Dict],
                                  cookies: Dict[str, str], max_redirects: int) -> Dict[str, Any]:
        """
        Perform a single HTTP request test.
        
        Args:
            url: Target URL
            method: HTTP method
            headers: Request headers
            body: Request body
            timeout: Request timeout
            follow_redirects: Whether to follow redirects
            verify_ssl: Whether to verify SSL certificates
            user_agent: User agent string
            auth: Authentication configuration
            cookies: Request cookies
            max_redirects: Maximum number of redirects
            
        Returns:
            Dictionary containing request test result
        """
        start_time = time.time()
        
        # Prepare headers
        request_headers = {'User-Agent': user_agent}
        request_headers.update(headers)
        
        # Prepare SSL context
        ssl_context = None
        if url.startswith('https://'):
            ssl_context = ssl.create_default_context()
            if not verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
        
        # Prepare authentication
        auth_obj = None
        if auth:
            if auth.get('type') == 'basic':
                auth_obj = aiohttp.BasicAuth(auth['username'], auth['password'])
        
        try:
            # Create timeout configuration
            timeout_config = aiohttp.ClientTimeout(total=timeout)
            
            # Create connector with SSL settings
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=1,
                limit_per_host=1
            )
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout_config,
                headers=request_headers,
                cookies=cookies,
                auth=auth_obj
            ) as session:
                
                # Track timing details
                dns_start = time.time()
                
                async with session.request(
                    method=method,
                    url=url,
                    data=body,
                    allow_redirects=follow_redirects,
                    max_redirects=max_redirects
                ) as response:
                    
                    # Read response content
                    content = await response.read()
                    response_time = (time.time() - start_time) * 1000
                    
                    # Get response details
                    result = {
                        'success': True,
                        'status_code': response.status,
                        'response_time': round(response_time, 2),
                        'content_length': len(content),
                        'headers': dict(response.headers),
                        'redirect_count': len(response.history),
                        'final_url': str(response.url),
                        'error': None,
                        'timestamp': start_time,
                        'timing': {
                            'total_time': round(response_time, 2),
                            'dns_lookup_time': None,  # Not easily available with aiohttp
                            'connect_time': None,     # Not easily available with aiohttp
                            'ssl_handshake_time': None,  # Not easily available with aiohttp
                            'first_byte_time': None   # Not easily available with aiohttp
                        }
                    }
                    
                    # Store content sample for analysis (first 1KB)
                    try:
                        content_sample = content[:1024].decode('utf-8', errors='ignore')
                        result['content_sample'] = content_sample
                    except Exception:
                        result['content_sample'] = None
                    
                    return result
                    
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return {
                'success': False,
                'status_code': None,
                'response_time': round(response_time, 2),
                'content_length': 0,
                'headers': {},
                'redirect_count': 0,
                'final_url': url,
                'error': f"Request timeout after {timeout}s",
                'timestamp': start_time,
                'timing': {
                    'total_time': round(response_time, 2),
                    'dns_lookup_time': None,
                    'connect_time': None,
                    'ssl_handshake_time': None,
                    'first_byte_time': None
                },
                'content_sample': None
            }
            
        except aiohttp.ClientError as e:
            response_time = (time.time() - start_time) * 1000
            return {
                'success': False,
                'status_code': None,
                'response_time': round(response_time, 2),
                'content_length': 0,
                'headers': {},
                'redirect_count': 0,
                'final_url': url,
                'error': f"Client error: {str(e)}",
                'timestamp': start_time,
                'timing': {
                    'total_time': round(response_time, 2),
                    'dns_lookup_time': None,
                    'connect_time': None,
                    'ssl_handshake_time': None,
                    'first_byte_time': None
                },
                'content_sample': None
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return {
                'success': False,
                'status_code': None,
                'response_time': round(response_time, 2),
                'content_length': 0,
                'headers': {},
                'redirect_count': 0,
                'final_url': url,
                'error': f"Unexpected error: {str(e)}",
                'timestamp': start_time,
                'timing': {
                    'total_time': round(response_time, 2),
                    'dns_lookup_time': None,
                    'connect_time': None,
                    'ssl_handshake_time': None,
                    'first_byte_time': None
                },
                'content_sample': None
            }
    
    def _calculate_metrics(self, request_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate HTTP request metrics from results.
        
        Args:
            request_results: List of request test results
            
        Returns:
            Dictionary containing calculated metrics
        """
        if not request_results:
            return {
                'total_requests': 0,
                'successful_requests': 0,
                'failed_requests': 0,
                'success_rate': 0.0,
                'min_response_time': None,
                'max_response_time': None,
                'avg_response_time': None,
                'stddev_response_time': None,
                'status_code_distribution': {},
                'content_length_avg': 0.0,
                'redirect_count_avg': 0.0,
                'ssl_handshake_time_avg': None,
                'dns_lookup_time_avg': None,
                'connect_time_avg': None,
                'first_byte_time_avg': None,
                'availability_score': 0.0
            }
        
        total_requests = len(request_results)
        successful_requests = sum(1 for result in request_results if result['success'])
        failed_requests = total_requests - successful_requests
        success_rate = (successful_requests / total_requests) * 100
        
        # Calculate response time statistics
        response_times = [result['response_time'] for result in request_results]
        min_response_time = min(response_times) if response_times else None
        max_response_time = max(response_times) if response_times else None
        avg_response_time = sum(response_times) / len(response_times) if response_times else None
        
        # Calculate standard deviation
        if response_times and len(response_times) > 1 and avg_response_time is not None:
            variance = sum((time - avg_response_time) ** 2 for time in response_times) / len(response_times)
            stddev_response_time = variance ** 0.5
        else:
            stddev_response_time = 0.0
        
        # Status code distribution
        status_code_distribution = {}
        for result in request_results:
            if result['status_code'] is not None:
                code = result['status_code']
                status_code_distribution[code] = status_code_distribution.get(code, 0) + 1
        
        # Content length average
        content_lengths = [result['content_length'] for result in request_results if result['success']]
        content_length_avg = sum(content_lengths) / len(content_lengths) if content_lengths else 0.0
        
        # Redirect count average
        redirect_counts = [result['redirect_count'] for result in request_results if result['success']]
        redirect_count_avg = sum(redirect_counts) / len(redirect_counts) if redirect_counts else 0.0
        
        # Calculate availability score
        # Based on success rate and response time consistency
        availability = success_rate
        if response_times and len(response_times) > 1 and avg_response_time and avg_response_time > 0:
            # Penalize high variance in response times
            cv = (stddev_response_time / avg_response_time)
            availability = max(0, availability - (cv * 5))  # Reduce score for high variance
        
        return {
            'total_requests': total_requests,
            'successful_requests': successful_requests,
            'failed_requests': failed_requests,
            'success_rate': round(success_rate, 1),
            'min_response_time': round(min_response_time, 2) if min_response_time is not None else None,
            'max_response_time': round(max_response_time, 2) if max_response_time is not None else None,
            'avg_response_time': round(avg_response_time, 2) if avg_response_time is not None else None,
            'stddev_response_time': round(stddev_response_time, 2) if stddev_response_time is not None else None,
            'status_code_distribution': status_code_distribution,
            'content_length_avg': round(content_length_avg, 2),
            'redirect_count_avg': round(redirect_count_avg, 1),
            'ssl_handshake_time_avg': None,  # Not implemented yet
            'dns_lookup_time_avg': None,     # Not implemented yet
            'connect_time_avg': None,        # Not implemented yet
            'first_byte_time_avg': None,     # Not implemented yet
            'availability_score': round(availability, 1)
        }
    
    def _determine_status(self, request_results: List[Dict[str, Any]], 
                         expected_status_codes: List[int],
                         content_check: Optional[str]) -> tuple:
        """
        Determine overall test status based on results.
        
        Args:
            request_results: List of request results
            expected_status_codes: List of expected HTTP status codes
            content_check: Content to check for in response (optional)
            
        Returns:
            Tuple of (status, error_message)
        """
        if not request_results:
            return ProtocolTestStatus.ERROR, "No request results available"
        
        successful_requests = [r for r in request_results if r['success']]
        
        if not successful_requests:
            return ProtocolTestStatus.FAILED, "All requests failed"
        
        # Check status codes
        status_code_failures = []
        for result in successful_requests:
            if result['status_code'] not in expected_status_codes:
                status_code_failures.append(result['status_code'])
        
        if status_code_failures:
            unique_failures = list(set(status_code_failures))
            return ProtocolTestStatus.ERROR, f"Unexpected status codes: {unique_failures}"
        
        # Check content if specified
        if content_check:
            content_failures = 0
            for result in successful_requests:
                if result.get('content_sample') and content_check not in result['content_sample']:
                    content_failures += 1
            
            if content_failures > 0:
                return ProtocolTestStatus.ERROR, f"Content check failed in {content_failures} requests"
        
        # Check success rate
        success_rate = (len(successful_requests) / len(request_results)) * 100
        if success_rate < 50.0:
            return ProtocolTestStatus.ERROR, f"Low success rate: {success_rate:.1f}%"
        
        # Check response times
        avg_response_time = sum(r['response_time'] for r in successful_requests) / len(successful_requests)
        if avg_response_time > 10000:  # 10 seconds
            return ProtocolTestStatus.ERROR, f"High response time: {avg_response_time:.1f}ms"
        
        return ProtocolTestStatus.SUCCESS, None


class HTTPSPlugin(HTTPPlugin):
    """
    HTTPS protocol plugin - extends HTTP plugin with HTTPS-specific settings.
    """
    
    def __init__(self):
        super().__init__()
        self._protocol_type = ProtocolType.HTTPS
        # Inherit all supported parameters from HTTP plugin
    
    def _build_url(self, target: str, port: Optional[int] = None) -> str:
        """
        Build HTTPS URL from target and port.
        
        Args:
            target: Target URL or hostname
            port: Port number (optional, defaults to 443)
            
        Returns:
            Complete HTTPS URL string
        """
        if target.startswith(('http://', 'https://')):
            # If scheme is already present, use as-is but prefer HTTPS
            if target.startswith('http://'):
                target = target.replace('http://', 'https://', 1)
            parsed = urlparse(target)
            if port and not parsed.port:
                # Add port to URL if not already present
                netloc = f"{parsed.hostname}:{port}"
                return f"https://{netloc}{parsed.path}"
            return target
        else:
            # Force HTTPS scheme
            if port and port != 443:
                return f"https://{target}:{port}"
            return f"https://{target}"
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default HTTPS configuration."""
        config = super().get_default_config()
        # Override defaults for HTTPS
        config['parameters']['verify_ssl'] = True
        return config