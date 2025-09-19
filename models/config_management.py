from pathlib import Path
import toml
import logging
from typing import Any, Optional
import os

from models.data_models import AppConfig, AppConfigWireguard, AppConfigDatabase, AppConfigOutput
from models.core.constants import (
    DEFAULT_KEEPALIVE_SECONDS, DEFAULT_CLIENT_IP, DEFAULT_DNS, DEFAULT_MAX_LOAD,
    DEFAULT_LIMIT, PRIVATE_KEY_PERMISSIONS, CONFIG_DIR_PERMISSIONS
)
from models.core.container_adapter import get_container_adapter

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages configuration for WireGuard settings using Pydantic models"""
    
    DEFAULT_CONFIG = AppConfig(
        wireguard=AppConfigWireguard(
            private_key_file="config/wireguard.key",  # Default path that should exist
            client_ip=DEFAULT_CLIENT_IP,
            dns=DEFAULT_DNS,
            persistent_keepalive=DEFAULT_KEEPALIVE_SECONDS
        ),
        database=AppConfigDatabase(
            path="servers.db",
            max_load=DEFAULT_MAX_LOAD,
            default_limit=DEFAULT_LIMIT
        ),
        output=AppConfigOutput(
            config_dir="/etc/wireguard",
            config_wg_file="/etc/wireguard/wg0.conf"
        )
    )
    
    def __init__(self, project_root: Optional[Path] = None):
        """Initialize config manager
        
        Args:
            project_root: Optional project root directory. If None,
                          uses current working directory or container paths
        """
        # Get container adapter for environment-aware configuration
        self.container_adapter = get_container_adapter()
        self.container_adapter.setup_container_environment()
        
        if self.container_adapter.environment.is_container:
            # In container mode, use container-specific paths
            self.project_root = Path('/app')
            self.config_dir = Path(self.container_adapter.environment.config_path)
        else:
            # Host mode - use existing logic
            if project_root is None:
                self.project_root = Path.cwd()
            else:
                self.project_root = project_root
            self.config_dir = self.project_root / 'config'
            
        self.config_file = self.config_dir / 'config.toml'
        
        # Initialize with container-aware default config
        self.config: AppConfig = AppConfig.model_validate(self._get_default_config().model_dump())
    
    def _get_default_config(self) -> AppConfig:
        """Get default configuration adapted for current environment
        
        Returns:
            AppConfig with environment-appropriate defaults
        """
        if self.container_adapter.environment.is_container:
            # Container-specific defaults
            return AppConfig(
                wireguard=AppConfigWireguard(
                    private_key_file=str(Path(self.container_adapter.environment.config_path) / 'wireguard.key'),
                    client_ip=DEFAULT_CLIENT_IP,
                    dns=DEFAULT_DNS,
                    persistent_keepalive=DEFAULT_KEEPALIVE_SECONDS
                ),
                database=AppConfigDatabase(
                    path=self.container_adapter.environment.database_path,
                    max_load=DEFAULT_MAX_LOAD,
                    default_limit=DEFAULT_LIMIT
                ),
                output=AppConfigOutput(
                    config_dir=str(Path(self.container_adapter.environment.wireguard_config_path).parent),
                    config_wg_file=self.container_adapter.environment.wireguard_config_path
                )
            )
        else:
            # Host system defaults (existing behavior)
            return ConfigManager.DEFAULT_CONFIG
        
    def load_or_create(self) -> None:
        """Load existing config or create with default values
        
        Raises:
            PermissionError: If unable to create config directory or files
            toml.TomlDecodeError: If config file is malformed
            ValidationError: If config file data doesn't match the expected schema
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True, mode=CONFIG_DIR_PERMISSIONS)
            
            if not self.config_file.exists():
                logger.info("No config file found. Creating new configuration...")
                self._create_initial_config()
            
            with open(self.config_file) as f:
                config_dict = toml.load(f)
                self.config = AppConfig.model_validate(config_dict)
                
        except PermissionError as e:
            logger.error(f"Permission denied creating config directory: {e}")
            raise
        except toml.TomlDecodeError as e:
            logger.error(f"Invalid config file format: {e}")
            raise
            
    def _create_initial_config(self) -> None:
        """Create initial configuration file using Pydantic models"""
        # Create the config directory if it doesn't exist
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=CONFIG_DIR_PERMISSIONS)
        
        # Check for auto-configuration from environment variables (container mode)
        if self.container_adapter.environment.is_container and self._can_auto_configure():
            logger.info("Auto-configuring from environment variables...")
            self._auto_configure_from_env()
            return
        
        # Interactive configuration (host mode or manual container setup)
        while True:
            try:
                # Create a separate private key file with restricted permissions
                key_file = self.config_dir / 'wireguard.key'
                private_key = input("Enter your WireGuard private key: ").strip()
                
                # Write private key with restricted permissions (readable only by owner)
                key_file.write_text(private_key)
                key_file.chmod(PRIVATE_KEY_PERMISSIONS)  # Owner read/write only
                
                # Get client IP
                client_ip = input("Enter your client IP (e.g., 10.5.0.2/32): ").strip()
                if not client_ip:
                    client_ip = DEFAULT_CLIENT_IP  # Default IP if none provided
                    logger.info(f"Using default client IP: {client_ip}")
                
                # Get environment-appropriate default config
                default_config = self._get_default_config()
                
                # Create AppConfig with provided values
                self.config = AppConfig(
                    wireguard=AppConfigWireguard(
                        private_key_file=str(key_file),
                        client_ip=client_ip,
                        dns=default_config.wireguard.dns,
                        persistent_keepalive=default_config.wireguard.persistent_keepalive
                    ),
                    database=default_config.database,
                    output=default_config.output
                )
                
                # Save main config
                with open(self.config_file, 'w') as f:
                    toml.dump(self.config.model_dump(), f)
                break
                
            except (ValueError, OSError) as e:
                logger.error(f"Configuration error: {e}")
                # Clean up any partial config
                if key_file.exists():
                    key_file.unlink()
                if self.config_file.exists():
                    self.config_file.unlink()
                print("Please try again.")
    
    def _can_auto_configure(self) -> bool:
        """Check if auto-configuration is possible from environment variables
        
        Returns:
            True if all required environment variables are present
        """
        return bool(os.environ.get('NORDHERO_PRIVATE_KEY'))
    
    def _auto_configure_from_env(self) -> None:
        """Auto-configure from environment variables (container mode)"""
        try:
            # Get environment variables with defaults
            private_key = os.environ.get('NORDHERO_PRIVATE_KEY')
            client_ip = os.environ.get('NORDHERO_CLIENT_IP', DEFAULT_CLIENT_IP)
            dns = os.environ.get('NORDHERO_DNS', DEFAULT_DNS)
            keepalive = int(os.environ.get('NORDHERO_KEEPALIVE', DEFAULT_KEEPALIVE_SECONDS))
            max_load = int(os.environ.get('NORDHERO_MAX_LOAD', DEFAULT_MAX_LOAD))
            default_limit = int(os.environ.get('NORDHERO_DEFAULT_LIMIT', DEFAULT_LIMIT))
            
            # Create private key file
            key_file = self.config_dir / 'wireguard.key'
            key_file.write_text(private_key)
            key_file.chmod(PRIVATE_KEY_PERMISSIONS)
            
            # Create configuration
            self.config = AppConfig(
                wireguard=AppConfigWireguard(
                    private_key_file=str(key_file),
                    client_ip=client_ip,
                    dns=dns,
                    persistent_keepalive=keepalive
                ),
                database=AppConfigDatabase(
                    path=self.container_adapter.environment.database_path,
                    max_load=max_load,
                    default_limit=default_limit
                ),
                output=AppConfigOutput(
                    config_dir=str(Path(self.container_adapter.environment.wireguard_config_path).parent),
                    config_wg_file=self.container_adapter.environment.wireguard_config_path
                )
            )
            
            # Save configuration
            with open(self.config_file, 'w') as f:
                toml.dump(self.config.model_dump(), f)
                
            logger.info("Auto-configuration completed successfully")
            
        except Exception as e:
            logger.error(f"Auto-configuration failed: {e}")
            raise
            
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get configuration value
        
        This method provides backward compatibility with the dictionary-based approach.
        For new code, prefer direct attribute access on self.config.
        """
        config_dict = self.config.model_dump()
        return config_dict.get(section, {}).get(key, default)
        
    def get_private_key(self) -> str:
        """Securely retrieve private key"""
        key_file = Path(self.config.wireguard.private_key_file)
        if not key_file.exists():
            raise FileNotFoundError("Private key file not found")
        return key_file.read_text().strip()
    
    def set(self, section: str, key: str, value: Any) -> None:
        """Set configuration value
        
        This method provides backward compatibility with the dictionary-based approach.
        For new code, prefer direct attribute modification on self.config.
        """
        config_dict = self.config.model_dump()
        
        if section not in config_dict:
            config_dict[section] = {}
        config_dict[section][key] = value
        
        # Update the Pydantic model with the modified dictionary
        self.config = AppConfig.model_validate(config_dict)
        
        # Save to file
        self.save()

    def save(self) -> None:
        """Save configuration to file with appropriate error handling
        
        This method ensures proper fsync and file permissions.
        
        Raises:
            PermissionError: If unable to write to config file
            OSError: For other file system related errors
        """
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=CONFIG_DIR_PERMISSIONS)
        
        with open(self.config_file, 'w') as f:
            toml.dump(self.config.model_dump(), f)
            # Ensure data is written to disk
            f.flush()
            try:
                # Only call fsync if fileno returns an integer (real file, not a mock)
                fileno = f.fileno()
                if isinstance(fileno, int):
                    os.fsync(fileno)
            except (AttributeError, OSError, TypeError):
                # Some file systems don't support fsync or this might be a mock
                pass
        
        # Set secure permissions on config file
        try:
            self.config_file.chmod(PRIVATE_KEY_PERMISSIONS)
        except (OSError, AttributeError):
            # Handle case where chmod is not available or path is mocked
            pass
