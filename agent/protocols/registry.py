"""
Global protocol registry instance and utility functions.

This module provides a singleton registry instance and convenience functions
for working with protocol plugins.
"""

from typing import Dict, List, Any
from .base import ProtocolRegistry, ProtocolPlugin, ProtocolConfig, ProtocolResult

# Global registry instance
_registry = None


def get_protocol_registry() -> ProtocolRegistry:
    """
    Get the global protocol registry instance.
    
    Returns:
        The global ProtocolRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ProtocolRegistry()
        # Auto-discover and register plugins
        _registry.discover_plugins()
    return _registry


def register_protocol(plugin_class) -> None:
    """
    Register a protocol plugin with the global registry.
    
    Args:
        plugin_class: The plugin class to register
    """
    registry = get_protocol_registry()
    registry.register(plugin_class)


def get_protocol_plugin(protocol: str) -> ProtocolPlugin:
    """
    Get a protocol plugin instance.
    
    Args:
        protocol: Protocol name
        
    Returns:
        Plugin instance
    """
    registry = get_protocol_registry()
    return registry.get_plugin(protocol)


def list_supported_protocols() -> List[str]:
    """
    Get list of all supported protocols.
    
    Returns:
        List of protocol names
    """
    registry = get_protocol_registry()
    return registry.list_protocols()


def is_protocol_supported(protocol: str) -> bool:
    """
    Check if a protocol is supported.
    
    Args:
        protocol: Protocol name
        
    Returns:
        True if supported, False otherwise
    """
    registry = get_protocol_registry()
    return registry.is_supported(protocol)


def get_protocol_info(protocol: str) -> Dict[str, Any]:
    """
    Get information about a protocol.
    
    Args:
        protocol: Protocol name
        
    Returns:
        Dictionary with protocol information
    """
    registry = get_protocol_registry()
    return registry.get_plugin_info(protocol)


async def execute_protocol_test(protocol: str, config: ProtocolConfig) -> ProtocolResult:
    """
    Execute a protocol test.
    
    Args:
        protocol: Protocol name
        config: Test configuration
        
    Returns:
        Test result
    """
    plugin = get_protocol_plugin(protocol)
    return await plugin.execute(config)