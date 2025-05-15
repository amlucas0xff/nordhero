"""
NordVPN WireGuard servers client module.
Fetches and processes WireGuard server information from NordVPN API.
"""
import logging
from typing import List
import requests
import csv
from datetime import datetime
import os
from requests.exceptions import RequestException

from .types import WireGuardServer, WireGuardServerInfo
from .exceptions import APIError, DataValidationError

logger = logging.getLogger(__name__)

class WireGuardClient:
    """Client for fetching NordVPN WireGuard server information"""
    
    API_URL = "https://api.nordvpn.com/v1/servers/recommendations"
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    def get_servers(self, limit: int = 5) -> List[WireGuardServerInfo]:
        """
        Fetch recommended WireGuard servers from NordVPN API.
        
        Args:
            limit: Maximum number of servers to return
            
        Returns:
            List of processed WireGuard server information
            
        Raises:
            APIError: If the API request fails
            DataValidationError: If response data is invalid
        """
        try:
            response = requests.get(
                self.API_URL,
                params={
                    "filters[servers_technologies][identifier]": "wireguard_udp",
                    "limit": limit
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            
        except RequestException as e:
            logger.error(f"Failed to fetch WireGuard servers: {e}")
            raise APIError(f"API request failed: {e}")
            
        try:
            servers = [WireGuardServer.parse_obj(server) for server in response.json()]
        except Exception as e:
            logger.error(f"Failed to parse server data: {e}")
            raise DataValidationError(f"Invalid server data: {e}")
            
        return [self._process_server(server) for server in servers]
    
    def export_to_csv(self, servers: List[WireGuardServerInfo], filepath: str = None) -> str:
        """
        Export server information to CSV file.
        
        Args:
            servers: List of WireGuardServerInfo objects
            filepath: Optional custom filepath, defaults to 'wireguard_servers_YYYY-MM-DD.csv'
            
        Returns:
            Path to the created CSV file
        """
        if filepath is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            filepath = f'wireguard_servers_{date_str}.csv'
            
        fieldnames = ['hostname', 'ip', 'country', 'city', 'load', 'public_key']
        
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for server in servers:
                writer.writerow({
                    'hostname': server.hostname,
                    'ip': server.ip,
                    'country': server.country,
                    'city': server.city,
                    'load': server.load,
                    'public_key': server.public_key
                })
        
        return filepath

    def _process_server(self, server: WireGuardServer) -> WireGuardServerInfo:
        """Extract relevant information from server data"""
        public_key = ""
        
        # Find WireGuard public key in technologies metadata
        for tech in server.technologies:
            if tech.identifier == "wireguard_udp":
                for meta in tech.metadata:
                    if meta.get("name") == "public_key":
                        public_key = meta.get("value", "")
                        break
        
        return WireGuardServerInfo(
            hostname=server.hostname,
            ip=server.station,
            country=server.locations[0].country.name,
            city=server.locations[0].country.city.name,
            load=server.load,
            publicKey=public_key
        )
