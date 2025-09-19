"""
Custom assertions for VPN testing.

This module provides specialized assertion utilities for verifying VPN
functionality, including connection status, configuration validity,
server details, and database integrity.
"""

import os
import sys
import re
import socket
import ipaddress
import requests
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from contextlib import contextmanager

logger = logging.getLogger('test')


class VPNAssertionError(AssertionError):
    """Error raised for VPN-specific assertion failures."""
    pass


@contextmanager
def assert_raises_vpn_error(match: Optional[str] = None):
    """
    Context manager to assert that a block of code raises a VPNAssertionError.
    
    Args:
        match: Regular expression pattern to match against the error message
    """
    try:
        yield
        raise AssertionError("VPNAssertionError not raised")
    except VPNAssertionError as e:
        if match and not re.search(match, str(e)):
            raise AssertionError(f"VPNAssertionError message '{str(e)}' does not match pattern '{match}'")


def assert_connected(status: Dict[str, Any]) -> None:
    """
    Assert that a VPN connection is established.
    
    Args:
        status: WireGuard status dictionary
        
    Raises:
        VPNAssertionError: If not connected
    """
    if not status:
        raise VPNAssertionError("No connection status available")
    
    if 'interface' not in status:
        raise VPNAssertionError("No interface found in connection status")
        
    if 'peers' not in status or not status['peers']:
        raise VPNAssertionError("No peers found in connection status")
    
    peer = status['peers'][0]
    if 'latest_handshake' not in peer or peer['latest_handshake'] <= 0:
        raise VPNAssertionError(f"No recent handshake found in connection status")


def assert_disconnected(status: Optional[Dict[str, Any]]) -> None:
    """
    Assert that a VPN connection is not established.
    
    Args:
        status: WireGuard status dictionary (or None if not connected)
        
    Raises:
        VPNAssertionError: If connected
    """
    if status and 'interface' in status and status['interface']:
        raise VPNAssertionError(f"VPN is still connected on interface {status['interface']}")


def assert_valid_wireguard_config(config_path: Union[str, Path]) -> None:
    """
    Assert that a WireGuard configuration file is valid.
    
    Args:
        config_path: Path to the WireGuard configuration file
        
    Raises:
        VPNAssertionError: If configuration is invalid
    """
    path = Path(config_path)
    if not path.exists():
        raise VPNAssertionError(f"WireGuard config file does not exist: {path}")
    
    config_text = path.read_text()
    
    # Check required sections
    required_sections = ['Interface', 'Peer']
    for section in required_sections:
        if f"[{section}]" not in config_text:
            raise VPNAssertionError(f"Required section [{section}] missing from WireGuard config")
    
    # Check required parameters
    required_interface_params = ['PrivateKey', 'Address']
    required_peer_params = ['PublicKey', 'AllowedIPs', 'Endpoint']
    
    for param in required_interface_params:
        if not re.search(f"{param} = .+", config_text):
            raise VPNAssertionError(f"Required parameter '{param}' missing from Interface section")
    
    for param in required_peer_params:
        if not re.search(f"{param} = .+", config_text):
            raise VPNAssertionError(f"Required parameter '{param}' missing from Peer section")
    
    # Validate IP addresses
    address_match = re.search(r"Address = (.+)", config_text)
    if address_match:
        address = address_match.group(1).strip()
        try:
            ipaddress.ip_network(address, strict=False)
        except ValueError as e:
            raise VPNAssertionError(f"Invalid Address in WireGuard config: {e}")
    
    # Validate endpoint
    endpoint_match = re.search(r"Endpoint = (.+)", config_text)
    if endpoint_match:
        endpoint = endpoint_match.group(1).strip()
        try:
            host, port_str = endpoint.rsplit(':', 1)
            port = int(port_str)
            if port < 1 or port > 65535:
                raise VPNAssertionError(f"Invalid port in Endpoint: {port}")
            # Try to resolve hostname
            socket.gethostbyname(host)
        except (ValueError, socket.error) as e:
            raise VPNAssertionError(f"Invalid Endpoint in WireGuard config: {e}")


def assert_valid_server(server: Dict[str, Any]) -> None:
    """
    Assert that a server entry contains all required fields.
    
    Args:
        server: Server dictionary
        
    Raises:
        VPNAssertionError: If server entry is invalid
    """
    required_fields = [
        'id', 'name', 'hostname', 'ip_address', 'country', 
        'country_code', 'load', 'public_key'
    ]
    
    for field in required_fields:
        if field not in server:
            raise VPNAssertionError(f"Required field '{field}' missing from server entry")
        
        if server[field] is None:
            raise VPNAssertionError(f"Field '{field}' is None in server entry")
    
    # Validate IP address
    try:
        ipaddress.ip_address(server['ip_address'])
    except ValueError as e:
        raise VPNAssertionError(f"Invalid IP address in server entry: {e}")
    
    # Validate public key (WireGuard public keys are base64 and 43-44 chars)
    if not re.match(r'^[A-Za-z0-9+/]{43}=?$', server['public_key']):
        raise VPNAssertionError(f"Invalid public key format in server entry")


def assert_database_integrity(db_path: Union[str, Path]) -> None:
    """
    Assert that a SQLite database is valid and has expected schema.
    
    Args:
        db_path: Path to the SQLite database
        
    Raises:
        VPNAssertionError: If database is invalid
    """
    path = Path(db_path)
    if not path.exists():
        raise VPNAssertionError(f"Database file does not exist: {path}")
    
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        
        # Check if servers table exists with required schema
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='servers'")
        if not cursor.fetchone():
            raise VPNAssertionError("Required table 'servers' not found in database")
        
        # Check table schema
        cursor.execute("PRAGMA table_info(servers)")
        columns = {row[1] for row in cursor.fetchall()}
        required_columns = {
            'id', 'name', 'hostname', 'ip_address', 'country', 
            'country_code', 'load', 'public_key'
        }
        
        missing_columns = required_columns - columns
        if missing_columns:
            raise VPNAssertionError(f"Required columns missing from 'servers' table: {missing_columns}")
            
        # Run integrity check
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()[0]
        if integrity_result != "ok":
            raise VPNAssertionError(f"Database integrity check failed: {integrity_result}")
            
        conn.close()
    except sqlite3.Error as e:
        raise VPNAssertionError(f"Database error: {e}")


def assert_ip_changed(original_ip: str, current_ip: Optional[str] = None) -> None:
    """
    Assert that the IP address has changed (e.g., after connecting to VPN).
    
    Args:
        original_ip: Original IP address before connecting
        current_ip: Current IP address (fetched automatically if None)
        
    Raises:
        VPNAssertionError: If IP has not changed
    """
    if current_ip is None:
        try:
            response = requests.get("https://api.ipify.org", timeout=5)
            current_ip = response.text.strip()
        except requests.RequestException as e:
            raise VPNAssertionError(f"Failed to get current IP address: {e}")
    
    if original_ip == current_ip:
        raise VPNAssertionError(f"IP address did not change after VPN operation. Still: {current_ip}")


def assert_systemd_service_status(service_name: str, expected_status: str) -> None:
    """
    Assert that a systemd service has the expected status.
    
    Args:
        service_name: Name of the systemd service
        expected_status: Expected status (e.g., 'active', 'inactive', 'enabled', 'disabled')
        
    Raises:
        VPNAssertionError: If service status doesn't match expected
    """
    import subprocess
    
    if expected_status in ('active', 'inactive'):
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True, text=True, check=False
            )
            actual_status = result.stdout.strip()
            if expected_status == 'active' and actual_status != 'active':
                raise VPNAssertionError(f"Service {service_name} is not active (status: {actual_status})")
            elif expected_status == 'inactive' and actual_status == 'active':
                raise VPNAssertionError(f"Service {service_name} is active but should be inactive")
        except subprocess.SubprocessError as e:
            raise VPNAssertionError(f"Failed to check service status: {e}")
            
    elif expected_status in ('enabled', 'disabled'):
        try:
            result = subprocess.run(
                ['systemctl', 'is-enabled', service_name],
                capture_output=True, text=True, check=False
            )
            actual_status = result.stdout.strip()
            if expected_status == 'enabled' and actual_status != 'enabled':
                raise VPNAssertionError(f"Service {service_name} is not enabled (status: {actual_status})")
            elif expected_status == 'disabled' and actual_status == 'enabled':
                raise VPNAssertionError(f"Service {service_name} is enabled but should be disabled")
        except subprocess.SubprocessError as e:
            raise VPNAssertionError(f"Failed to check if service is enabled: {e}")
    else:
        raise ValueError(f"Invalid expected_status: {expected_status}. Expected one of: active, inactive, enabled, disabled") 