from dataclasses import dataclass
from typing import Dict

from models.data_models import ServerDBRecord
from models.core.constants import DEFAULT_KEEPALIVE_SECONDS, WIREGUARD_PORT

@dataclass
class WireGuardConfig:
    """WireGuard configuration model"""
    private_key: str
    client_ip: str
    dns: str
    public_key: str
    endpoint: str
    persistent_keepalive: int = DEFAULT_KEEPALIVE_SECONDS
    
    def generate(self) -> str:
        """Generate WireGuard configuration string"""
        return f"""[Interface]
PrivateKey={self.private_key}
Address={self.client_ip}
DNS={self.dns}
SaveConfig=true

[Peer]
PublicKey={self.public_key}
AllowedIPs=0.0.0.0/0, ::/0
Endpoint={self.endpoint}:{WIREGUARD_PORT}
PersistentKeepalive={self.persistent_keepalive}
"""
    
    @classmethod
    def from_server(cls, server: ServerDBRecord, config_manager) -> 'WireGuardConfig':
        """Create config from server info and config manager"""
        return cls(
            private_key=config_manager.get_private_key(),
            client_ip=config_manager.get('wireguard', 'client_ip'),
            dns=config_manager.get('wireguard', 'dns'),
            public_key=server.public_key,
            endpoint=server.ip,
            persistent_keepalive=config_manager.get('wireguard', 'persistent_keepalive')
        )
