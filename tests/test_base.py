"""
Base test classes for NordVPN WireGuard Manager.

This module provides direct API access to application functions
without relying on menu navigation, enabling programmatic testing.
"""

import os
import sys
import pytest
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List, Tuple, Union

from models.config_management import ConfigManager
from models.database_management import DatabaseClient, init_database
from models.connection_management import (
    manage_connection, 
    check_wireguard_status, 
    update_server_list,
    show_top_servers,
    select_vpn_endpoint,
    select_by_country,
    generate_wireguard_config
)
from models.service_management import (
    check_systemd_available,
    check_systemd_status,
    manage_autostart
)
from api.nordvpn_client.wireguard import WireGuardClient


class DirectAPITestError(Exception):
    """Exception raised for errors in the Direct API Test framework."""
    pass


class DirectAPITestBase:
    """
    Base class for testing with direct API access to application functions.
    
    This class provides direct access to the application's functionality
    without relying on menu navigation, enabling programmatic testing.
    """
    
    def __init__(self, config_manager: ConfigManager):
        """
        Initialize the test base with a configuration manager.
        
        Args:
            config_manager: A ConfigManager instance for the test
        """
        self.config_manager = config_manager
        self.logger = logging.getLogger('test')
        
        # Initialize key application components
        self._init_components()
    
    def _init_components(self):
        """Initialize application components for testing."""
        # Database client
        db_path = self.config_manager.get('database', 'path')
        self.db_client = DatabaseClient(db_path)
        
        # WireGuard client
        self.wg_client = WireGuardClient()
    
    # Direct API access for application functions
    
    def update_server_list(self, limit: int = 0) -> Dict[str, Any]:
        """
        Direct API access to update the server database.
        
        Args:
            limit: Number of servers to fetch (0 for unlimited)
            
        Returns:
            Dictionary with update results
        """
        return update_server_list(self.config_manager, limit)
    
    def get_top_servers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top servers by load.
        
        Args:
            limit: Maximum number of servers to return
            
        Returns:
            List of server dictionaries
        """
        servers = self.db_client.get_top_servers(limit)
        return servers if servers else []
    
    def get_country_servers(self, country_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top servers for a specific country.
        
        Args:
            country_code: Two-letter country code
            limit: Maximum number of servers to return
            
        Returns:
            List of server dictionaries
        """
        servers = self.db_client.get_country_servers(country_code, limit)
        return servers if servers else []
    
    def generate_config(self, server_id: int) -> str:
        """
        Generate WireGuard configuration for a specific server.
        
        Args:
            server_id: ID of the server to use
            
        Returns:
            Path to generated configuration file
        """
        server = self.db_client.get_server_by_id(server_id)
        if not server:
            raise DirectAPITestError(f"Server with ID {server_id} not found")
        
        return generate_wireguard_config(self.config_manager, server)
    
    def connect(self) -> Dict[str, Any]:
        """
        Connect to WireGuard VPN.
        
        Returns:
            Connection result
        """
        return manage_connection(self.config_manager, "up")
    
    def disconnect(self) -> Dict[str, Any]:
        """
        Disconnect from WireGuard VPN.
        
        Returns:
            Disconnection result
        """
        return manage_connection(self.config_manager, "down")
    
    def restart(self) -> Dict[str, Any]:
        """
        Restart WireGuard VPN connection.
        
        Returns:
            Restart result
        """
        return manage_connection(self.config_manager, "restart")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get current connection status.
        
        Returns:
            Status dictionary
        """
        return check_wireguard_status()
    
    def manage_systemd_service(self, action: str) -> Dict[str, Any]:
        """
        Manage systemd service.
        
        Args:
            action: Service action ('create', 'enable', 'disable', 'start', 'stop')
            
        Returns:
            Action result
        """
        if not check_systemd_available():
            raise DirectAPITestError("Systemd not available on this system")
        
        return manage_autostart(self.config_manager, action) 