"""
Tests for container functionality and adapter.

This module tests the container detection, adaptation, and functionality
when running NordHero in Docker containers.
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from models.core.container_adapter import ContainerAdapter, get_container_adapter
from models.config_management import ConfigManager
from models.connection_management import check_wireguard_status
from models.service_management import check_systemd_available, manage_autostart


class TestContainerAdapter:
    """Test container detection and adaptation functionality"""
    
    def test_container_detection_with_dockerenv(self):
        """Test container detection using .dockerenv file"""
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            adapter = ContainerAdapter()
            assert adapter.environment.is_container is True
            assert adapter.environment.container_type == 'docker'
    
    def test_container_detection_with_env_var(self):
        """Test container detection using environment variable"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            with patch('pathlib.Path.exists', return_value=False):
                adapter = ContainerAdapter()
                assert adapter.environment.is_container is True
    
    def test_container_detection_with_cgroup(self):
        """Test container detection using cgroup"""
        mock_cgroup_content = "1:name=systemd:/docker/abc123"
        with patch('builtins.open', mock_open(read_data=mock_cgroup_content)):
            with patch('pathlib.Path.exists', return_value=False):
                with patch('os.getpid', return_value=2):
                    adapter = ContainerAdapter()
                    assert adapter.environment.is_container is True
    
    def test_host_detection(self):
        """Test detection of host (non-container) environment"""
        with patch('pathlib.Path.exists', return_value=False):
            with patch('os.getpid', return_value=1234):
                with patch('builtins.open', side_effect=FileNotFoundError):
                    adapter = ContainerAdapter()
                    assert adapter.environment.is_container is False
    
    def test_command_prefix_in_container(self):
        """Test command prefix returns empty list in container"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            adapter = ContainerAdapter()
            assert adapter.get_command_prefix() == []
    
    def test_command_prefix_on_host_as_root(self):
        """Test command prefix returns empty list when running as root on host"""
        with patch('os.getuid', return_value=0):
            with patch('pathlib.Path.exists', return_value=False):
                adapter = ContainerAdapter()
                assert adapter.get_command_prefix() == []
    
    def test_command_prefix_on_host_as_user(self):
        """Test command prefix returns sudo when running as user on host"""
        with patch('os.getuid', return_value=1000):
            with patch('os.path.exists', return_value=True):
                with patch('pathlib.Path.exists', return_value=False):
                    adapter = ContainerAdapter()
                    assert adapter.get_command_prefix() == ['sudo']
    
    def test_container_paths(self):
        """Test container-specific paths are used"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            adapter = ContainerAdapter()
            paths = adapter.get_config_paths()
            assert '/app' in paths['config_dir']
            assert '/app' in paths['database_path']
            assert '/etc/wireguard' in paths['wireguard_config']
    
    def test_systemd_disabled_in_container(self):
        """Test systemd management is disabled in containers"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            adapter = ContainerAdapter()
            assert adapter.should_manage_systemd() is False


class TestContainerConfigManager:
    """Test ConfigManager with container adapter"""
    
    @pytest.fixture
    def temp_container_dir(self):
        """Create temporary directory for container tests"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    def test_container_config_paths(self, temp_container_dir):
        """Test ConfigManager uses container paths when in container mode"""
        with patch.dict(os.environ, {
            'NORDHERO_CONTAINER_MODE': 'true',
            'NORDHERO_CONFIG_PATH': str(temp_container_dir / 'config'),
            'NORDHERO_DATABASE_PATH': str(temp_container_dir / 'data/servers.db'),
            'NORDHERO_WG_CONFIG_PATH': '/etc/wireguard/wg0.conf'
        }):
            with patch('pathlib.Path.mkdir'):
                config_manager = ConfigManager(temp_container_dir)
                assert str(temp_container_dir / 'config') in str(config_manager.config_dir)
    
    def test_auto_configuration_from_env(self, temp_container_dir):
        """Test auto-configuration from environment variables"""
        with patch.dict(os.environ, {
            'NORDHERO_CONTAINER_MODE': 'true',
            'NORDHERO_PRIVATE_KEY': 'test_private_key_123',
            'NORDHERO_CLIENT_IP': '10.5.0.5/32',
            'NORDHERO_DNS': '1.1.1.1',
            'NORDHERO_CONFIG_PATH': str(temp_container_dir / 'config'),
            'NORDHERO_DATABASE_PATH': str(temp_container_dir / 'data/servers.db')
        }):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text'):
                    with patch('pathlib.Path.chmod'):
                        with patch('builtins.open', mock_open()):
                            config_manager = ConfigManager(temp_container_dir)
                            config_manager.load_or_create()
                            
                            # Verify auto-configuration was used
                            assert str(config_manager.config.wireguard.client_ip) == '10.5.0.5/32'
                            assert str(config_manager.config.wireguard.dns) == '1.1.1.1'
    
    def test_container_default_config(self, temp_container_dir):
        """Test container-specific default configuration"""
        with patch.dict(os.environ, {
            'NORDHERO_CONTAINER_MODE': 'true',
            'NORDHERO_CONFIG_PATH': str(temp_container_dir / 'config'),
            'NORDHERO_DATABASE_PATH': str(temp_container_dir / 'data/servers.db')
        }):
            with patch('pathlib.Path.mkdir'):
                config_manager = ConfigManager(temp_container_dir)
                default_config = config_manager._get_default_config()
                
                assert temp_container_dir.name in default_config.database.path


class TestContainerConnectionManagement:
    """Test connection management in container environment"""
    
    def test_wg_commands_without_sudo(self):
        """Test WireGuard commands don't use sudo in container"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = ""
                
                check_wireguard_status(quiet=True)
                
                # Verify no sudo was used in the command
                called_commands = [call[0][0] for call in mock_run.call_args_list]
                for command in called_commands:
                    assert 'sudo' not in command
    
    def test_container_privilege_messages(self):
        """Test appropriate privilege messages are shown in containers"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = Exception("Test error")
                
                with patch('builtins.print') as mock_print:
                    try:
                        check_wireguard_status(quiet=False)
                    except:
                        pass
                    
                    # Check that container-appropriate message was printed
                    printed_messages = [str(call) for call in mock_print.call_args_list]
                    container_messages = [msg for msg in printed_messages if 'as root' in msg]
                    assert len(container_messages) > 0


class TestContainerServiceManagement:
    """Test service management in container environment"""
    
    def test_systemd_unavailable_in_container(self):
        """Test systemd is reported as unavailable in containers"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            assert check_systemd_available() is False
    
    def test_manage_autostart_container_message(self):
        """Test manage_autostart shows appropriate container message"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            with patch('builtins.print') as mock_print:
                with patch('models.ui_helpers.safe_input', return_value=''):
                    config_manager = MagicMock()
                    manage_autostart(config_manager)
                    
                    # Check that container-specific message was shown
                    printed_messages = [str(call) for call in mock_print.call_args_list]
                    container_messages = [msg for msg in printed_messages if 'Container Environment' in msg]
                    assert len(container_messages) > 0


class TestContainerEnvironmentInfo:
    """Test container environment information gathering"""
    
    def test_environment_info_collection(self):
        """Test comprehensive environment info collection"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            adapter = ContainerAdapter()
            env_info = adapter.get_environment_info()
            
            assert 'is_container' in env_info
            assert 'container_type' in env_info
            assert 'has_systemd' in env_info
            assert 'has_sudo' in env_info
            assert 'config_path' in env_info
            assert 'database_path' in env_info
            assert 'wireguard_config_path' in env_info
            assert 'uid' in env_info
            assert 'gid' in env_info
            assert 'pid' in env_info
            
            assert env_info['is_container'] is True
    
    def test_setup_container_environment(self):
        """Test container environment setup"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            with patch('pathlib.Path.mkdir') as mock_mkdir:
                adapter = ContainerAdapter()
                adapter.setup_container_environment()
                
                # Verify directories were created
                assert mock_mkdir.called


class TestContainerIntegration:
    """Integration tests for container functionality"""
    
    def test_global_adapter_singleton(self):
        """Test global adapter instance is properly shared"""
        adapter1 = get_container_adapter()
        adapter2 = get_container_adapter()
        assert adapter1 is adapter2
    
    def test_container_mode_override(self):
        """Test forcing container mode via environment variable"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': 'true'}):
            # Clear any existing adapter instance
            import models.core.container_adapter
            models.core.container_adapter._adapter_instance = None
            
            adapter = get_container_adapter()
            assert adapter.environment.is_container is True
    
    @pytest.mark.parametrize('env_var,expected', [
        ('true', True),
        ('1', True),
        ('yes', True),
        ('false', False),
        ('0', False),
        ('no', False),
        ('', False),
    ])
    def test_container_mode_env_values(self, env_var, expected):
        """Test different values for container mode environment variable"""
        with patch.dict(os.environ, {'NORDHERO_CONTAINER_MODE': env_var}):
            with patch('pathlib.Path.exists', return_value=False):
                with patch('os.getpid', return_value=999):
                    # Clear any existing adapter instance
                    import models.core.container_adapter
                    models.core.container_adapter._adapter_instance = None
                    
                    adapter = ContainerAdapter()
                    assert adapter.environment.is_container is expected


if __name__ == '__main__':
    pytest.main([__file__])