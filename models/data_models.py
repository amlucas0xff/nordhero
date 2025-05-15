from pydantic import BaseModel, FilePath, DirectoryPath, IPvAnyNetwork, IPvAnyAddress
from typing import List, Optional, Tuple


class ServerDBRecord(BaseModel):
    """Represents a server record from the database."""
    hostname: str
    ip: str
    country: str
    city: str
    load: int
    public_key: str


class WGTransferInfo(BaseModel):
    """Information about data transfer for a WireGuard connection."""
    received: str
    sent: str


class WGConnectionDetails(BaseModel):
    """Details about a WireGuard connection."""
    public_key: Optional[str] = None
    endpoint: Optional[str] = None
    latest_handshake: Optional[str] = None
    transfer: WGTransferInfo


class ConnectedServerAppInfo(BaseModel):
    """Server information after matching with database."""
    country: str
    city: str
    load: int
    hostname: str
    endpoint: Optional[str] = None  # The actual endpoint IP from `wg show`
    latest_handshake: Optional[str] = None
    transfer: WGTransferInfo
    found_by: Optional[str] = None  # e.g., 'ip', 'public_key'


class WGStatusReport(BaseModel):
    """Overall status report for WireGuard connection."""
    is_connected: bool
    interface_details: Optional[WGConnectionDetails] = None  # Raw from `wg show interface`
    app_server_info: Optional[ConnectedServerAppInfo] = None  # After DB lookup
    raw_unmatched_details: Optional[WGConnectionDetails] = None  # If connected but not found in DB


class SystemdServiceStatus(BaseModel):
    """Status information for a systemd service."""
    exists: bool
    enabled: bool
    active: bool
    user_mode: bool
    path: Optional[str] = None


class AppConfigWireguard(BaseModel):
    """WireGuard-specific configuration."""
    private_key_file: str  # Changed from FilePath to str
    client_ip: IPvAnyNetwork
    dns: IPvAnyAddress
    persistent_keepalive: int


class AppConfigDatabase(BaseModel):
    """Database-specific configuration."""
    path: str  # Changed from FilePath to str
    max_load: int
    default_limit: int


class AppConfigOutput(BaseModel):
    """Output-specific configuration."""
    config_dir: str  # Changed from DirectoryPath to str
    config_wg_file: str  # Changed from FilePath to str


class AppConfig(BaseModel):
    """Main application configuration."""
    wireguard: AppConfigWireguard
    database: AppConfigDatabase
    output: AppConfigOutput 