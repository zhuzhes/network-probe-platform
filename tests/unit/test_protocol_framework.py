"""
Unit tests for the protocol plugin framework.

Tests the base protocol plugin system, registry, and plugin discovery.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch
from dataclasses import dataclass

from agent.protocols.base import (
    ProtocolPlugin, ProtocolRegistry, ProtocolResult, ProtocolConfig,
    ProtocolType, ProtocolTestStatus, ProtocolError
)
from agent.protocols.registry import (
    get_protocol_registry, register_protocol, get_protocol_plugin,
    list_supported_protocols, is_protocol_supported, get_protocol_info,
    execute_protocol_test
)


class MockProtocolPlugin(ProtocolPlugin):
    """Mock protocol plugin for testing."""
    
    def __init__(self):
        super().__init__()
        self._protocol_type = ProtocolType.TCP
        self._supported_parameters = {'param1', 'param2'}
    
    async def execute(self, config: ProtocolConfig) -> ProtocolResult:
        """Mock execute method."""
        if config.target == 'fail':
            raise ProtocolError("Mock failure", protocol='mock', target=config.target)
        
        return ProtocolResult(
            protocol='mock',
            target=config.target,
            port=config.port,
            status=ProtocolTestStatus.SUCCESS,
            duration_ms=100.0,
            metrics={'test_metric': 42},
            raw_data={'response': 'ok'}
        )
    
    def validate_config(self, config: ProtocolConfig) -> bool:
        """Mock validate method."""
        return config.target != 'invalid'
    
    def get_metrics_description(self) -> dict:
        """Mock metrics description."""
        return {'test_metric': 'A test metric'}


class TestProtocolResult:
    """Test ProtocolResult class."""
    
    def test_protocol_result_creation(self):
        """Test creating a ProtocolResult."""
        result = ProtocolResult(
            protocol='test',
            target='example.com',
            port=80,
            status=ProtocolTestStatus.SUCCESS,
            duration_ms=150.5,
            metrics={'latency': 50.0},
            raw_data={'response_code': 200}
        )
        
        assert result.protocol == 'test'
        assert result.target == 'example.com'
        assert result.port == 80
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.duration_ms == 150.5
        assert result.metrics == {'latency': 50.0}
        assert result.raw_data == {'response_code': 200}
    
    def test_protocol_result_to_dict(self):
        """Test converting ProtocolResult to dictionary."""
        result = ProtocolResult(
            protocol='test',
            target='example.com',
            status=ProtocolTestStatus.ERROR,
            error_message='Test error'
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['protocol'] == 'test'
        assert result_dict['target'] == 'example.com'
        assert result_dict['status'] == 'error'
        assert result_dict['error_message'] == 'Test error'
        assert 'timestamp' in result_dict
        assert 'duration_ms' in result_dict


class TestProtocolConfig:
    """Test ProtocolConfig class."""
    
    def test_protocol_config_creation(self):
        """Test creating a ProtocolConfig."""
        config = ProtocolConfig(
            target='example.com',
            port=443,
            timeout=10.0,
            parameters={'ssl': True}
        )
        
        assert config.target == 'example.com'
        assert config.port == 443
        assert config.timeout == 10.0
        assert config.parameters == {'ssl': True}
    
    def test_protocol_config_defaults(self):
        """Test ProtocolConfig with default values."""
        config = ProtocolConfig(target='example.com')
        
        assert config.target == 'example.com'
        assert config.port is None
        assert config.timeout == 5.0
        assert config.parameters == {}


class TestProtocolPlugin:
    """Test ProtocolPlugin base class."""
    
    def test_plugin_properties(self):
        """Test plugin properties."""
        plugin = MockProtocolPlugin()
        
        assert plugin.name == 'mockprotocol'
        assert plugin.protocol_type == ProtocolType.TCP
        assert plugin.supported_parameters == {'param1', 'param2'}
    
    def test_plugin_default_config(self):
        """Test plugin default configuration."""
        plugin = MockProtocolPlugin()
        default_config = plugin.get_default_config()
        
        assert default_config['timeout'] == 5.0
        assert default_config['parameters'] == {}
    
    def test_plugin_metrics_description(self):
        """Test plugin metrics description."""
        plugin = MockProtocolPlugin()
        metrics = plugin.get_metrics_description()
        
        assert metrics == {'test_metric': 'A test metric'}
    
    @pytest.mark.asyncio
    async def test_plugin_execute_success(self):
        """Test successful plugin execution."""
        plugin = MockProtocolPlugin()
        config = ProtocolConfig(target='example.com', port=80)
        
        result = await plugin.execute(config)
        
        assert result.protocol == 'mock'
        assert result.target == 'example.com'
        assert result.port == 80
        assert result.status == ProtocolTestStatus.SUCCESS
        assert result.duration_ms == 100.0
        assert result.metrics == {'test_metric': 42}
    
    @pytest.mark.asyncio
    async def test_plugin_execute_failure(self):
        """Test plugin execution failure."""
        plugin = MockProtocolPlugin()
        config = ProtocolConfig(target='fail')
        
        with pytest.raises(ProtocolError) as exc_info:
            await plugin.execute(config)
        
        assert str(exc_info.value) == "Mock failure"
        assert exc_info.value.protocol == 'mock'
        assert exc_info.value.target == 'fail'
    
    def test_plugin_validate_config(self):
        """Test plugin configuration validation."""
        plugin = MockProtocolPlugin()
        
        valid_config = ProtocolConfig(target='example.com')
        invalid_config = ProtocolConfig(target='invalid')
        
        assert plugin.validate_config(valid_config) is True
        assert plugin.validate_config(invalid_config) is False


class TestProtocolRegistry:
    """Test ProtocolRegistry class."""
    
    def test_registry_creation(self):
        """Test creating a registry."""
        registry = ProtocolRegistry()
        
        assert len(registry.list_protocols()) == 0
    
    def test_register_plugin(self):
        """Test registering a plugin."""
        registry = ProtocolRegistry()
        registry.register(MockProtocolPlugin)
        
        protocols = registry.list_protocols()
        assert 'mockprotocol' in protocols
    
    def test_register_invalid_plugin(self):
        """Test registering an invalid plugin."""
        registry = ProtocolRegistry()
        
        class InvalidPlugin:
            pass
        
        with pytest.raises(ValueError, match="must inherit from ProtocolPlugin"):
            registry.register(InvalidPlugin)
    
    def test_register_duplicate_plugin(self):
        """Test registering a duplicate plugin."""
        registry = ProtocolRegistry()
        registry.register(MockProtocolPlugin)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(MockProtocolPlugin)
    
    def test_unregister_plugin(self):
        """Test unregistering a plugin."""
        registry = ProtocolRegistry()
        registry.register(MockProtocolPlugin)
        
        assert registry.is_supported('mockprotocol')
        
        registry.unregister('mockprotocol')
        
        assert not registry.is_supported('mockprotocol')
    
    def test_get_plugin(self):
        """Test getting a plugin instance."""
        registry = ProtocolRegistry()
        registry.register(MockProtocolPlugin)
        
        plugin = registry.get_plugin('mockprotocol')
        
        assert isinstance(plugin, MockProtocolPlugin)
        assert plugin.name == 'mockprotocol'
    
    def test_get_plugin_singleton(self):
        """Test that get_plugin returns the same instance."""
        registry = ProtocolRegistry()
        registry.register(MockProtocolPlugin)
        
        plugin1 = registry.get_plugin('mockprotocol')
        plugin2 = registry.get_plugin('mockprotocol')
        
        assert plugin1 is plugin2
    
    def test_get_unsupported_plugin(self):
        """Test getting an unsupported plugin."""
        registry = ProtocolRegistry()
        
        with pytest.raises(ValueError, match="Unsupported protocol"):
            registry.get_plugin('nonexistent')
    
    def test_is_supported(self):
        """Test checking if protocol is supported."""
        registry = ProtocolRegistry()
        
        assert not registry.is_supported('mockprotocol')
        
        registry.register(MockProtocolPlugin)
        
        assert registry.is_supported('mockprotocol')
    
    def test_get_plugin_info(self):
        """Test getting plugin information."""
        registry = ProtocolRegistry()
        registry.register(MockProtocolPlugin)
        
        info = registry.get_plugin_info('mockprotocol')
        
        assert info['name'] == 'mockprotocol'
        assert info['protocol_type'] == 'tcp'
        assert set(info['supported_parameters']) == {'param1', 'param2'}
        assert info['default_config']['timeout'] == 5.0
        assert info['metrics_description'] == {'test_metric': 'A test metric'}
    
    def test_get_plugin_info_unsupported(self):
        """Test getting info for unsupported plugin."""
        registry = ProtocolRegistry()
        
        with pytest.raises(ValueError, match="Unsupported protocol"):
            registry.get_plugin_info('nonexistent')
    
    def test_discover_plugins(self):
        """Test plugin discovery."""
        registry = ProtocolRegistry()
        
        # Manually register a plugin first to test the discovery doesn't break
        registry.register(MockProtocolPlugin)
        initial_count = len(registry.list_protocols())
        
        # Call discover_plugins - it should not break even if no new plugins are found
        registry.discover_plugins()
        
        # Should still have at least the manually registered plugin
        protocols = registry.list_protocols()
        assert len(protocols) >= initial_count


class TestRegistryModule:
    """Test the registry module functions."""
    
    def setup_method(self):
        """Reset global registry before each test."""
        import agent.protocols.registry
        agent.protocols.registry._registry = None
    
    def test_get_protocol_registry(self):
        """Test getting the global registry."""
        registry1 = get_protocol_registry()
        registry2 = get_protocol_registry()
        
        assert registry1 is registry2  # Should be singleton
    
    def test_register_protocol(self):
        """Test registering a protocol globally."""
        register_protocol(MockProtocolPlugin)
        
        assert is_protocol_supported('mockprotocol')
    
    def test_get_protocol_plugin(self):
        """Test getting a protocol plugin globally."""
        register_protocol(MockProtocolPlugin)
        
        plugin = get_protocol_plugin('mockprotocol')
        
        assert isinstance(plugin, MockProtocolPlugin)
    
    def test_list_supported_protocols(self):
        """Test listing supported protocols."""
        register_protocol(MockProtocolPlugin)
        
        protocols = list_supported_protocols()
        
        assert 'mockprotocol' in protocols
    
    def test_get_protocol_info_global(self):
        """Test getting protocol info globally."""
        register_protocol(MockProtocolPlugin)
        
        info = get_protocol_info('mockprotocol')
        
        assert info['name'] == 'mockprotocol'
    
    @pytest.mark.asyncio
    async def test_execute_protocol_test(self):
        """Test executing a protocol test globally."""
        register_protocol(MockProtocolPlugin)
        
        config = ProtocolConfig(target='example.com', port=80)
        result = await execute_protocol_test('mockprotocol', config)
        
        assert result.protocol == 'mock'
        assert result.target == 'example.com'
        assert result.status == ProtocolTestStatus.SUCCESS


class TestProtocolError:
    """Test ProtocolError exception."""
    
    def test_protocol_error_creation(self):
        """Test creating a ProtocolError."""
        error = ProtocolError("Test error", protocol='test', target='example.com')
        
        assert str(error) == "Test error"
        assert error.protocol == 'test'
        assert error.target == 'example.com'
    
    def test_protocol_error_minimal(self):
        """Test creating a minimal ProtocolError."""
        error = ProtocolError("Test error")
        
        assert str(error) == "Test error"
        assert error.protocol is None
        assert error.target is None