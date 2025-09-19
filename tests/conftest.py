"""
Test configuration and shared fixtures for NordVPN WireGuard Manager
"""
import os
import sys
import pytest
import tempfile
import logging
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path to ensure imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.config_management import ConfigManager
from models.database_management import DatabaseClient
from models.connection_management import check_wireguard_status
from api.nordvpn_client.wireguard import WireGuardClient


# Configure logging for tests
@pytest.fixture(scope="session", autouse=True)
def configure_test_logging():
    """Configure logging for tests"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    # Create a test logger
    logger = logging.getLogger('test')
    return logger


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)


@pytest.fixture
def config_manager(temp_dir):
    """Create a ConfigManager instance for testing with a temporary config directory"""
    manager = ConfigManager(temp_dir)
    manager.config_file = temp_dir / 'config.toml'
    
    # Load default config
    manager.config = manager.DEFAULT_CONFIG.model_copy()
    
    # Create temporary files for paths in config
    private_key_file = temp_dir / 'wireguard.key'
    private_key_file.write_text('test_private_key')
    private_key_file.chmod(0o600)
    
    # Update the config using proper Pydantic model access
    manager.config.wireguard.private_key_file = str(private_key_file)
    manager.config.wireguard.client_ip = '10.5.0.2/32'
    manager.config.database.path = str(temp_dir / 'test_servers.db')
    manager.config.output.config_dir = str(temp_dir / 'wireguard')
    manager.config.output.config_wg_file = str(temp_dir / 'wireguard/wg0.conf')
    
    # Create output dir
    output_dir = temp_dir / 'wireguard'
    output_dir.mkdir(exist_ok=True)
    
    return manager


@pytest.fixture
def mock_db_client():
    """Create a mock database client"""
    mock_client = Mock(spec=DatabaseClient)
    return mock_client


@pytest.fixture
def mock_wg_client():
    """Create a mock WireGuard client"""
    mock_client = Mock(spec=WireGuardClient)
    return mock_client


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for testing system commands"""
    with patch('subprocess.run') as mock_run:
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = "Mock command output"
        mock_run.return_value = mock_process
        yield mock_run


@pytest.fixture
def mock_connection_status():
    """Mock connection status for testing connection management"""
    with patch('models.connection_management.check_wireguard_status') as mock_status:
        mock_status.return_value = {
            'interface': 'wg0',
            'public_key': 'test_public_key',
            'listening_port': 51820,
            'peers': [{
                'public_key': 'peer_public_key',
                'endpoint': '1.2.3.4:51820',
                'allowed_ips': '0.0.0.0/0',
                'latest_handshake': 1620000000,
                'transfer_rx': 1024,
                'transfer_tx': 2048,
                'persistent_keepalive': 25
            }]
        }
        yield mock_status 