"""
Base protocol plugin framework for network probe agents.

This module defines the abstract base class and interfaces that all protocol
plugins must implement, as well as the plugin registry system.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
from enum import Enum


class ProtocolType(Enum):
    """Supported protocol types."""
    ICMP = "icmp"
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"


class ProtocolTestStatus(Enum):
    """Test execution status."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ERROR = "error"
    FAILED = "failed"


@dataclass
class ProtocolResult:
    """
    Result of a protocol test execution.
    
    Contains all metrics and metadata from a protocol test.
    """
    protocol: str
    target: str
    port: Optional[int] = None
    status: ProtocolTestStatus = ProtocolTestStatus.SUCCESS
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            'protocol': self.protocol,
            'target': self.target,
            'port': self.port,
            'status': self.status.value,
            'duration_ms': self.duration_ms,
            'timestamp': self.timestamp,
            'error_message': self.error_message,
            'metrics': self.metrics,
            'raw_data': self.raw_data
        }


@dataclass
class ProtocolConfig:
    """Configuration for protocol test execution."""
    target: str
    port: Optional[int] = None
    timeout: float = 5.0
    parameters: Dict[str, Any] = field(default_factory=dict)


class ProtocolPlugin(ABC):
    """
    Abstract base class for all protocol plugins.
    
    All protocol implementations must inherit from this class and implement
    the required abstract methods.
    """
    
    def __init__(self):
        self._name = self.__class__.__name__.lower().replace('plugin', '')
        self._protocol_type = None
        self._supported_parameters = set()
    
    @property
    def name(self) -> str:
        """Get the plugin name."""
        return self._name
    
    @property
    def protocol_type(self) -> ProtocolType:
        """Get the protocol type this plugin handles."""
        return self._protocol_type
    
    @property
    def supported_parameters(self) -> set:
        """Get the set of supported configuration parameters."""
        return self._supported_parameters.copy()
    
    @abstractmethod
    async def execute(self, config: ProtocolConfig) -> ProtocolResult:
        """
        Execute the protocol test.
        
        Args:
            config: Configuration for the test execution
            
        Returns:
            ProtocolResult containing test results and metrics
            
        Raises:
            ProtocolError: If test execution fails
        """
        pass
    
    @abstractmethod
    def validate_config(self, config: ProtocolConfig) -> bool:
        """
        Validate the configuration for this protocol.
        
        Args:
            config: Configuration to validate
            
        Returns:
            True if configuration is valid, False otherwise
        """
        pass
    
    def get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration parameters for this protocol.
        
        Returns:
            Dictionary of default configuration values
        """
        return {
            'timeout': 5.0,
            'parameters': {}
        }
    
    def get_metrics_description(self) -> Dict[str, str]:
        """
        Get description of metrics this protocol provides.
        
        Returns:
            Dictionary mapping metric names to descriptions
        """
        return {}


class ProtocolError(Exception):
    """Exception raised by protocol plugins."""
    
    def __init__(self, message: str, protocol: str = None, target: str = None):
        super().__init__(message)
        self.protocol = protocol
        self.target = target


class ProtocolRegistry:
    """
    Registry for protocol plugins.
    
    Manages registration, discovery, and instantiation of protocol plugins.
    """
    
    def __init__(self):
        self._plugins: Dict[str, Type[ProtocolPlugin]] = {}
        self._instances: Dict[str, ProtocolPlugin] = {}
    
    def register(self, plugin_class: Type[ProtocolPlugin]) -> None:
        """
        Register a protocol plugin class.
        
        Args:
            plugin_class: The plugin class to register
            
        Raises:
            ValueError: If plugin is invalid or already registered
        """
        if not issubclass(plugin_class, ProtocolPlugin):
            raise ValueError(f"Plugin {plugin_class} must inherit from ProtocolPlugin")
        
        # Create temporary instance to get plugin info
        temp_instance = plugin_class()
        plugin_name = temp_instance.name
        
        if plugin_name in self._plugins:
            raise ValueError(f"Plugin '{plugin_name}' is already registered")
        
        self._plugins[plugin_name] = plugin_class
        print(f"Registered protocol plugin: {plugin_name}")
    
    def unregister(self, plugin_name: str) -> None:
        """
        Unregister a protocol plugin.
        
        Args:
            plugin_name: Name of the plugin to unregister
        """
        if plugin_name in self._plugins:
            del self._plugins[plugin_name]
        if plugin_name in self._instances:
            del self._instances[plugin_name]
    
    def get_plugin(self, protocol: str) -> ProtocolPlugin:
        """
        Get a plugin instance for the specified protocol.
        
        Args:
            protocol: Protocol name
            
        Returns:
            Plugin instance
            
        Raises:
            ValueError: If protocol is not supported
        """
        if protocol not in self._plugins:
            raise ValueError(f"Unsupported protocol: {protocol}")
        
        # Use singleton pattern for plugin instances
        if protocol not in self._instances:
            self._instances[protocol] = self._plugins[protocol]()
        
        return self._instances[protocol]
    
    def list_protocols(self) -> List[str]:
        """
        Get list of registered protocol names.
        
        Returns:
            List of protocol names
        """
        return list(self._plugins.keys())
    
    def is_supported(self, protocol: str) -> bool:
        """
        Check if a protocol is supported.
        
        Args:
            protocol: Protocol name to check
            
        Returns:
            True if protocol is supported, False otherwise
        """
        return protocol in self._plugins
    
    def get_plugin_info(self, protocol: str) -> Dict[str, Any]:
        """
        Get information about a protocol plugin.
        
        Args:
            protocol: Protocol name
            
        Returns:
            Dictionary containing plugin information
            
        Raises:
            ValueError: If protocol is not supported
        """
        if not self.is_supported(protocol):
            raise ValueError(f"Unsupported protocol: {protocol}")
        
        plugin = self.get_plugin(protocol)
        return {
            'name': plugin.name,
            'protocol_type': plugin.protocol_type.value if plugin.protocol_type else None,
            'supported_parameters': list(plugin.supported_parameters),
            'default_config': plugin.get_default_config(),
            'metrics_description': plugin.get_metrics_description()
        }
    
    def discover_plugins(self) -> None:
        """
        Discover and auto-register protocol plugins.
        
        This method scans for available protocol plugins and registers them
        automatically. It looks for classes that inherit from ProtocolPlugin
        in the protocols package.
        """
        import importlib
        import pkgutil
        import inspect
        
        try:
            # Import all modules in the protocols package
            import agent.protocols as protocols_package
            
            for importer, modname, ispkg in pkgutil.iter_modules(protocols_package.__path__):
                if modname in ('base', 'registry'):  # Skip base and registry modules
                    continue
                    
                try:
                    module = importlib.import_module(f'agent.protocols.{modname}')
                    
                    # Find all classes that inherit from ProtocolPlugin
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (issubclass(obj, ProtocolPlugin) and 
                            obj != ProtocolPlugin and 
                            not inspect.isabstract(obj)):
                            try:
                                self.register(obj)
                            except ValueError as e:
                                print(f"Failed to register plugin {name}: {e}")
                                
                except ImportError as e:
                    print(f"Failed to import protocol module {modname}: {e}")
                    
        except ImportError as e:
            print(f"Failed to import protocols package: {e}")