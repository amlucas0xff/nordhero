"""
Container adapter for running NordHero in Docker containers.

This module provides detection and adaptation logic for running the application
in containerized environments, handling differences in filesystem, networking,
and system management.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ContainerEnvironment:
    """Container environment configuration"""
    is_container: bool
    container_type: Optional[str] = None
    has_systemd: bool = False
    has_sudo: bool = False
    config_path: str = "/app/config"
    database_path: str = "/app/data/servers.db"
    wireguard_config_path: str = "/etc/wireguard/wg0.conf"


class ContainerAdapter:
    """Adapter for running NordHero in container environments"""
    
    def __init__(self):
        self.environment = self._detect_environment()
        
    def _detect_environment(self) -> ContainerEnvironment:
        """Detect if we're running in a container and what type
        
        Returns:
            ContainerEnvironment with detected settings
        """
        is_container = self._is_running_in_container()
        container_type = self._detect_container_type() if is_container else None
        has_systemd = self._has_systemd() and not is_container
        has_sudo = self._has_sudo(is_container)
        
        # Container-specific paths
        if is_container:
            config_path = os.environ.get('NORDHERO_CONFIG_PATH', '/app/config')
            database_path = os.environ.get('NORDHERO_DATABASE_PATH', '/app/data/servers.db')
            wireguard_config_path = os.environ.get('NORDHERO_WG_CONFIG_PATH', '/etc/wireguard/wg0.conf')
        else:
            # Host system paths (existing behavior)
            config_path = "config"
            database_path = "servers.db"
            wireguard_config_path = "/etc/wireguard/wg0.conf"
        
        return ContainerEnvironment(
            is_container=is_container,
            container_type=container_type,
            has_systemd=has_systemd,
            has_sudo=has_sudo,
            config_path=config_path,
            database_path=database_path,
            wireguard_config_path=wireguard_config_path
        )
    
    def _is_running_in_container(self) -> bool:
        """Check if we're running inside a container
        
        Returns:
            True if running in a container
        """
        # Check multiple indicators for container environment
        indicators = [
            # Docker creates .dockerenv file
            Path('/.dockerenv').exists(),
            
            # Container environment variable
            os.environ.get('CONTAINER') is not None,
            
            # Check cgroup for container indicators
            self._check_cgroup_for_container(),
            
            # Check if we're running as PID 1 (common in containers)
            os.getpid() == 1,
            
            # Custom environment variable for forcing container mode
            os.environ.get('NORDHERO_CONTAINER_MODE', '').lower() in ('true', '1', 'yes')
        ]
        
        return any(indicators)
    
    def _check_cgroup_for_container(self) -> bool:
        """Check cgroup file for container indicators
        
        Returns:
            True if cgroup indicates container environment
        """
        try:
            with open('/proc/1/cgroup', 'r') as f:
                cgroup_content = f.read()
                return any(indicator in cgroup_content for indicator in [
                    'docker', 'containerd', 'lxc', 'kubepods'
                ])
        except (OSError, IOError):
            return False
    
    def _detect_container_type(self) -> Optional[str]:
        """Detect the type of container we're running in
        
        Returns:
            Container type string or None
        """
        if Path('/.dockerenv').exists():
            return 'docker'
        if os.environ.get('KUBERNETES_SERVICE_HOST'):
            return 'kubernetes'
        if 'lxc' in os.environ.get('container', ''):
            return 'lxc'
        return 'unknown'
    
    def _has_systemd(self) -> bool:
        """Check if systemd is available
        
        Returns:
            True if systemd is available
        """
        return Path('/run/systemd/system').exists()
    
    def _has_sudo(self, is_container: bool = False) -> bool:
        """Check if sudo is available and needed
        
        Args:
            is_container: Whether we're running in a container
        
        Returns:
            True if sudo is available and we're not root
        """
        # In containers, we typically run as root
        if is_container:
            return False
        
        # On host system, check if we're root or have sudo
        return os.getuid() != 0 and os.path.exists('/usr/bin/sudo')
    
    def get_command_prefix(self) -> list:
        """Get command prefix for system commands
        
        Returns:
            List of command prefix elements (e.g., ['sudo'] or [])
        """
        if self.environment.is_container or os.getuid() == 0:
            return []  # No sudo needed in container or when running as root
        return ['sudo']
    
    def get_config_paths(self) -> Dict[str, str]:
        """Get appropriate configuration paths for the environment
        
        Returns:
            Dictionary of configuration paths
        """
        return {
            'config_dir': self.environment.config_path,
            'database_path': self.environment.database_path,
            'wireguard_config': self.environment.wireguard_config_path
        }
    
    def setup_container_environment(self) -> None:
        """Setup the container environment with necessary directories and permissions"""
        if not self.environment.is_container:
            return
        
        # Create necessary directories
        directories = [
            Path(self.environment.config_path),
            Path(self.environment.database_path).parent,
            Path(self.environment.wireguard_config_path).parent
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created directory: {directory}")
            except OSError as e:
                logger.error(f"Failed to create directory {directory}: {e}")
    
    def should_manage_systemd(self) -> bool:
        """Check if systemd management should be enabled
        
        Returns:
            True if systemd management should be enabled
        """
        return self.environment.has_systemd and not self.environment.is_container
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Get comprehensive environment information
        
        Returns:
            Dictionary with environment details
        """
        return {
            'is_container': self.environment.is_container,
            'container_type': self.environment.container_type,
            'has_systemd': self.environment.has_systemd,
            'has_sudo': self.environment.has_sudo,
            'config_path': self.environment.config_path,
            'database_path': self.environment.database_path,
            'wireguard_config_path': self.environment.wireguard_config_path,
            'uid': os.getuid(),
            'gid': os.getgid(),
            'pid': os.getpid()
        }


# Global adapter instance
_adapter_instance = None


def get_container_adapter() -> ContainerAdapter:
    """Get the global container adapter instance
    
    Returns:
        ContainerAdapter instance
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ContainerAdapter()
    return _adapter_instance


def is_running_in_container() -> bool:
    """Quick check if we're running in a container
    
    Returns:
        True if running in a container
    """
    return get_container_adapter().environment.is_container


def should_use_sudo() -> bool:
    """Check if sudo should be used for system commands
    
    Returns:
        True if sudo should be used
    """
    adapter = get_container_adapter()
    return adapter.environment.has_sudo and not adapter.environment.is_container