"""
Unit tests for HTTP/HTTPS protocol plugin.

Tests the HTTP and HTTPS protocol implementations including request handling,
metrics calculation, and error scenarios.
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
import aiohttp
import ssl

from agent.protocols.http import HTTPPlugin, HTTPSPlugin
from agent.protocols.base import (
    ProtocolConfig, ProtocolResult, ProtocolTestStatus, ProtocolError
)


class TestHTTPPlugin:
    """Test cases for HTTP protocol plugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = HTTPPlugin()
    
    def test_plugin_initialization(self):
        """Test plugin initialization."""
        assert self.plugin.name == 'http'
        assert self.plugin.protocol_type.value == 'http'
        assert 'method' in self.plugin.supported_parameters
        assert 'headers' in self.plugin.supported_parameters
        assert 'body' in self.plugin.supported_parameters
        assert 'verify_ssl' in self.plugin.supported_parameters
    
    def test_get_default_config(self):
        """Test default configuration."""
        config = self.plugin.get_default_config()
        
        assert config['timeout'] == 10.0
        assert config['parameters']['method'] == 'GET'
        assert config['parameters']['follow_redirects'] is True
        assert config['parameters']['verify_ssl'] is True
        assert config['parameters']['status_codes'] == [200]
    
    def test_get_metrics_description(self):
        """Test metrics description."""
        metrics = self.plugin.get_metrics_description()
        
        assert 'total_requests' in metrics
        assert 'successful_requests' in metrics
        assert 'avg_response_time' in metrics
        assert 'status_code_distribution' in metrics
        assert 'availability_score' in metrics
    
    def test_validate_config_valid(self):
        """Test configuration validation with valid config."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={
                'method': 'GET',
                'headers': {'User-Agent': 'Test'},
                'status_codes': [200, 201]
            }
        )
        
        assert self.plugin.validate_config(config) is True
    
    def test_validate_config_invalid_target(self):
        """Test configuration validation with invalid target."""
        config = ProtocolConfig(target='', timeout=5.0)
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_method(self):
        """Test configuration validation with invalid method."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={'method': 'INVALID'}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_headers(self):
        """Test configuration validation with invalid headers."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={'headers': 'invalid'}
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_validate_config_invalid_status_codes(self):
        """Test configuration validation with invalid status codes."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={'status_codes': [999]}  # Invalid status code
        )
        
        assert self.plugin.validate_config(config) is False
    
    def test_build_url_with_scheme(self):
        """Test URL building with existing scheme."""
        url = self.plugin._build_url('http://example.com/path', None)
        assert url == 'http://example.com/path'
        
        url = self.plugin._build_url('https://example.com', 8080)
        assert url == 'https://example.com:8080'
    
    def test_build_url_without_scheme(self):
        """Test URL building without scheme."""
        url = self.plugin._build_url('example.com', None)
        assert url == 'http://example.com'
        
        url = self.plugin._build_url('example.com', 8080)
        assert url == 'http://example.com:8080'
        
        url = self.plugin._build_url('example.com', 443)
        assert url == 'https://example.com'
    
    def test_is_valid_url(self):
        """Test URL validation."""
        assert self.plugin._is_valid_url('http://example.com') is True
        assert self.plugin._is_valid_url('https://example.com') is True
        assert self.plugin._is_valid_url('example.com') is True
        assert self.plugin._is_valid_url('192.168.1.1') is True
        assert self.plugin._is_valid_url('') is False
        assert self.plugin._is_valid_url('   ') is False
    
    @pytest.mark.asyncio
    async def test_single_http_request_success(self):
        """Test successful HTTP request."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.headers = {'Content-Type': 'text/html'}
        mock_response.url = 'http://example.com'
        mock_response.history = []
        mock_response.read = AsyncMock(return_value=b'<html>Test content</html>')
        
        # Create a proper async context manager mock
        mock_response_context = AsyncMock()
        mock_response_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_context.__aexit__ = AsyncMock(return_value=None)
        
        mock_session = Mock()
        mock_session.request = Mock(return_value=mock_response_context)
        
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session_context):
            with patch('aiohttp.TCPConnector'):
                result = await self.plugin._single_http_request(
                    url='http://example.com',
                    method='GET',
                    headers={},
                    body=None,
                    timeout=5.0,
                    follow_redirects=True,
                    verify_ssl=True,
                    user_agent='Test',
                    auth=None,
                    cookies={},
                    max_redirects=10
                )
                
                assert result['success'] is True
                assert result['status_code'] == 200
                assert result['content_length'] == 25
                assert result['redirect_count'] == 0
                assert result['error'] is None
                assert 'response_time' in result
                assert result['content_sample'] == '<html>Test content</html>'
    
    @pytest.mark.asyncio
    async def test_single_http_request_timeout(self):
        """Test HTTP request timeout."""
        mock_session = Mock()
        mock_session.request = Mock(side_effect=asyncio.TimeoutError())
        
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session_context):
            with patch('aiohttp.TCPConnector'):
                result = await self.plugin._single_http_request(
                    url='http://example.com',
                    method='GET',
                    headers={},
                    body=None,
                    timeout=1.0,
                    follow_redirects=True,
                    verify_ssl=True,
                    user_agent='Test',
                    auth=None,
                    cookies={},
                    max_redirects=10
                )
                
                assert result['success'] is False
                assert result['status_code'] is None
                assert 'timeout' in result['error'].lower()
                assert result['content_length'] == 0
    
    @pytest.mark.asyncio
    async def test_single_http_request_client_error(self):
        """Test HTTP request client error."""
        mock_session = Mock()
        mock_session.request = Mock(side_effect=aiohttp.ClientError("Connection failed"))
        
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession', return_value=mock_session_context):
            with patch('aiohttp.TCPConnector'):
                result = await self.plugin._single_http_request(
                    url='http://example.com',
                    method='GET',
                    headers={},
                    body=None,
                    timeout=5.0,
                    follow_redirects=True,
                    verify_ssl=True,
                    user_agent='Test',
                    auth=None,
                    cookies={},
                    max_redirects=10
                )
                
                assert result['success'] is False
                assert result['status_code'] is None
                assert 'client error' in result['error'].lower()
    
    def test_calculate_metrics_empty_results(self):
        """Test metrics calculation with empty results."""
        metrics = self.plugin._calculate_metrics([])
        
        assert metrics['total_requests'] == 0
        assert metrics['successful_requests'] == 0
        assert metrics['success_rate'] == 0.0
        assert metrics['avg_response_time'] is None
        assert metrics['status_code_distribution'] == {}
        assert metrics['availability_score'] == 0.0
    
    def test_calculate_metrics_with_results(self):
        """Test metrics calculation with actual results."""
        results = [
            {
                'success': True,
                'status_code': 200,
                'response_time': 100.0,
                'content_length': 1000,
                'redirect_count': 0
            },
            {
                'success': True,
                'status_code': 200,
                'response_time': 150.0,
                'content_length': 1200,
                'redirect_count': 1
            },
            {
                'success': False,
                'status_code': None,
                'response_time': 5000.0,
                'content_length': 0,
                'redirect_count': 0
            }
        ]
        
        metrics = self.plugin._calculate_metrics(results)
        
        assert metrics['total_requests'] == 3
        assert metrics['successful_requests'] == 2
        assert metrics['failed_requests'] == 1
        assert metrics['success_rate'] == 66.7
        assert metrics['min_response_time'] == 100.0
        assert metrics['max_response_time'] == 5000.0
        assert metrics['avg_response_time'] == 1750.0
        assert metrics['status_code_distribution'] == {200: 2}
        assert metrics['content_length_avg'] == 1100.0
        assert metrics['redirect_count_avg'] == 0.5
    
    def test_determine_status_success(self):
        """Test status determination for successful requests."""
        results = [
            {'success': True, 'status_code': 200, 'response_time': 100.0, 'content_sample': 'Hello World'},
            {'success': True, 'status_code': 200, 'response_time': 150.0, 'content_sample': 'Hello World'}
        ]
        
        status, error = self.plugin._determine_status(results, [200], None)
        assert status == ProtocolTestStatus.SUCCESS
        assert error is None
    
    def test_determine_status_all_failed(self):
        """Test status determination when all requests fail."""
        results = [
            {'success': False, 'status_code': None, 'response_time': 5000.0},
            {'success': False, 'status_code': None, 'response_time': 5000.0}
        ]
        
        status, error = self.plugin._determine_status(results, [200], None)
        assert status == ProtocolTestStatus.FAILED
        assert 'all requests failed' in error.lower()
    
    def test_determine_status_wrong_status_code(self):
        """Test status determination with wrong status codes."""
        results = [
            {'success': True, 'status_code': 404, 'response_time': 100.0},
            {'success': True, 'status_code': 500, 'response_time': 150.0}
        ]
        
        status, error = self.plugin._determine_status(results, [200], None)
        assert status == ProtocolTestStatus.ERROR
        assert 'unexpected status codes' in error.lower()
    
    def test_determine_status_content_check_failure(self):
        """Test status determination with content check failure."""
        results = [
            {'success': True, 'status_code': 200, 'response_time': 100.0, 'content_sample': 'Wrong content'},
            {'success': True, 'status_code': 200, 'response_time': 150.0, 'content_sample': 'Also wrong'}
        ]
        
        status, error = self.plugin._determine_status(results, [200], 'Expected content')
        assert status == ProtocolTestStatus.ERROR
        assert 'content check failed' in error.lower()
    
    def test_determine_status_low_success_rate(self):
        """Test status determination with low success rate."""
        results = [
            {'success': True, 'status_code': 200, 'response_time': 100.0},
            {'success': False, 'status_code': None, 'response_time': 5000.0},
            {'success': False, 'status_code': None, 'response_time': 5000.0}
        ]
        
        status, error = self.plugin._determine_status(results, [200], None)
        assert status == ProtocolTestStatus.ERROR
        assert 'low success rate' in error.lower()
    
    def test_determine_status_high_response_time(self):
        """Test status determination with high response time."""
        results = [
            {'success': True, 'status_code': 200, 'response_time': 15000.0},
            {'success': True, 'status_code': 200, 'response_time': 12000.0}
        ]
        
        status, error = self.plugin._determine_status(results, [200], None)
        assert status == ProtocolTestStatus.ERROR
        assert 'high response time' in error.lower()
    
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful execution of HTTP test."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={'method': 'GET', 'request_attempts': 1}
        )
        
        # Mock the HTTP request method
        mock_result = {
            'success': True,
            'status_code': 200,
            'response_time': 100.0,
            'content_length': 1000,
            'headers': {'Content-Type': 'text/html'},
            'redirect_count': 0,
            'final_url': 'http://example.com',
            'error': None,
            'timestamp': time.time(),
            'timing': {'total_time': 100.0},
            'content_sample': '<html>Test</html>',
            'attempt': 1
        }
        
        with patch.object(self.plugin, '_test_http_requests', return_value=[mock_result]):
            result = await self.plugin.execute(config)
            
            assert isinstance(result, ProtocolResult)
            assert result.protocol == 'http'
            assert result.target == 'http://example.com'
            assert result.status == ProtocolTestStatus.SUCCESS
            assert result.error_message is None
            assert 'total_requests' in result.metrics
            assert 'successful_requests' in result.metrics
    
    @pytest.mark.asyncio
    async def test_execute_invalid_config(self):
        """Test execution with invalid configuration."""
        config = ProtocolConfig(target='', timeout=5.0)
        
        with pytest.raises(ProtocolError) as exc_info:
            await self.plugin.execute(config)
        
        assert 'invalid configuration' in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_execute_with_exception(self):
        """Test execution when an exception occurs."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={'method': 'GET'}
        )
        
        with patch.object(self.plugin, '_test_http_requests', side_effect=Exception("Test error")):
            with pytest.raises(ProtocolError) as exc_info:
                await self.plugin.execute(config)
            
            assert 'http test failed' in str(exc_info.value).lower()
            assert 'Test error' in str(exc_info.value)


class TestHTTPSPlugin:
    """Test cases for HTTPS protocol plugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = HTTPSPlugin()
    
    def test_plugin_initialization(self):
        """Test HTTPS plugin initialization."""
        assert self.plugin.name == 'https'
        assert self.plugin.protocol_type.value == 'https'
        # Should inherit all parameters from HTTP plugin
        assert 'method' in self.plugin.supported_parameters
        assert 'verify_ssl' in self.plugin.supported_parameters
    
    def test_get_default_config(self):
        """Test HTTPS default configuration."""
        config = self.plugin.get_default_config()
        
        assert config['timeout'] == 10.0
        assert config['parameters']['verify_ssl'] is True  # Should be True for HTTPS
    
    def test_build_url_force_https(self):
        """Test URL building forces HTTPS scheme."""
        url = self.plugin._build_url('example.com', None)
        assert url == 'https://example.com'
        
        url = self.plugin._build_url('example.com', 8443)
        assert url == 'https://example.com:8443'
        
        # Should convert HTTP to HTTPS
        url = self.plugin._build_url('http://example.com', None)
        assert url == 'https://example.com'
    
    def test_build_url_with_port_443(self):
        """Test URL building with default HTTPS port."""
        url = self.plugin._build_url('example.com', 443)
        assert url == 'https://example.com'  # Port 443 should not be shown
    
    @pytest.mark.asyncio
    async def test_execute_https_success(self):
        """Test successful execution of HTTPS test."""
        config = ProtocolConfig(
            target='https://example.com',
            timeout=5.0,
            parameters={'method': 'GET', 'request_attempts': 1}
        )
        
        # Mock the HTTP request method
        mock_result = {
            'success': True,
            'status_code': 200,
            'response_time': 100.0,
            'content_length': 1000,
            'headers': {'Content-Type': 'text/html'},
            'redirect_count': 0,
            'final_url': 'https://example.com',
            'error': None,
            'timestamp': time.time(),
            'timing': {'total_time': 100.0},
            'content_sample': '<html>Test</html>',
            'attempt': 1
        }
        
        with patch.object(self.plugin, '_test_http_requests', return_value=[mock_result]):
            result = await self.plugin.execute(config)
            
            assert isinstance(result, ProtocolResult)
            assert result.protocol == 'https'
            assert result.target == 'https://example.com'
            assert result.status == ProtocolTestStatus.SUCCESS


class TestHTTPPluginIntegration:
    """Integration tests for HTTP plugin."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.plugin = HTTPPlugin()
    
    @pytest.mark.asyncio
    async def test_test_http_requests_multiple_attempts(self):
        """Test multiple HTTP request attempts."""
        mock_results = [
            {
                'success': True,
                'status_code': 200,
                'response_time': 100.0,
                'content_length': 1000,
                'headers': {},
                'redirect_count': 0,
                'final_url': 'http://example.com',
                'error': None,
                'timestamp': time.time(),
                'timing': {'total_time': 100.0},
                'content_sample': 'test'
            },
            {
                'success': False,
                'status_code': None,
                'response_time': 5000.0,
                'content_length': 0,
                'headers': {},
                'redirect_count': 0,
                'final_url': 'http://example.com',
                'error': 'Timeout',
                'timestamp': time.time(),
                'timing': {'total_time': 5000.0},
                'content_sample': None
            }
        ]
        
        with patch.object(self.plugin, '_single_http_request', side_effect=mock_results):
            results = await self.plugin._test_http_requests(
                url='http://example.com',
                method='GET',
                headers={},
                body=None,
                timeout=5.0,
                follow_redirects=True,
                verify_ssl=True,
                user_agent='Test',
                auth=None,
                cookies={},
                max_redirects=10,
                attempts=2,
                retry_interval=0.1
            )
            
            assert len(results) == 2
            assert results[0]['attempt'] == 1
            assert results[1]['attempt'] == 2
            assert results[0]['success'] is True
            assert results[1]['success'] is False
    
    def test_auth_configuration(self):
        """Test authentication configuration validation."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={
                'auth': {
                    'type': 'basic',
                    'username': 'user',
                    'password': 'pass'
                }
            }
        )
        
        assert self.plugin.validate_config(config) is True
    
    def test_custom_headers_configuration(self):
        """Test custom headers configuration."""
        config = ProtocolConfig(
            target='http://example.com',
            timeout=5.0,
            parameters={
                'headers': {
                    'Authorization': 'Bearer token123',
                    'X-Custom-Header': 'custom-value'
                }
            }
        )
        
        assert self.plugin.validate_config(config) is True
    
    def test_post_request_with_body(self):
        """Test POST request configuration with body."""
        config = ProtocolConfig(
            target='http://example.com/api',
            timeout=5.0,
            parameters={
                'method': 'POST',
                'headers': {'Content-Type': 'application/json'},
                'body': '{"key": "value"}'
            }
        )
        
        assert self.plugin.validate_config(config) is True


if __name__ == '__main__':
    pytest.main([__file__])