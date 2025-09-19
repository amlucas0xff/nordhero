from pathlib import Path
import logging
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
from pydantic import ValidationError

from models.data_models import AppConfig, AppConfigWireguard, AppConfigDatabase, AppConfigOutput
from models.core.constants import WIREGUARD_KEY_LENGTH, WIREGUARD_KEY_SUFFIX

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Stores validation check results"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]

class ConfigValidator:
    """Validates WireGuard configuration requirements
    
    This class handles runtime validation checks that cannot
    be handled by Pydantic's built-in validation alone.
    """
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> ValidationResult:
        """Run all validation checks
        
        Returns:
            ValidationResult: Result of validation containing errors and warnings
        """
        self.errors.clear()
        self.warnings.clear()

        # Get the AppConfig instance from config_manager
        config = self.config_manager.config

        # Validate using Pydantic model first
        try:
            # Re-validate the model to ensure it's still valid
            # This will catch any type errors or field constraints
            AppConfig.model_validate(config.model_dump())
        except ValidationError as e:
            # Add each validation error to our errors list
            for error in e.errors():
                self.errors.append(f"Config error: {error['loc']}, {error['msg']}")
        except ValueError as e:
            # Also handle ValueErrors which might come from validation in tests
            self.errors.append(f"Config error: {str(e)}")
        
        # Perform additional runtime checks
        self._check_private_key(config.wireguard)
        self._check_client_ip(config.wireguard)
        self._check_output_directory_permissions(config.output)
        self._check_database_existence(config.database)
        
        return ValidationResult(
            is_valid=len(self.errors) == 0,
            errors=self.errors.copy(),
            warnings=self.warnings.copy()
        )

    def _check_private_key(self, wireguard_config: AppConfigWireguard) -> None:
        """Validate private key exists and format
        
        Args:
            wireguard_config: WireGuard configuration section
        """
        try:
            private_key = self.config_manager.get_private_key()
            if len(private_key) != WIREGUARD_KEY_LENGTH or not private_key.endswith(WIREGUARD_KEY_SUFFIX):
                self.errors.append("WireGuard private key appears to be invalid")
        except FileNotFoundError:
            self.errors.append("WireGuard private key file is missing")
        except PermissionError:
            self.errors.append("Cannot read WireGuard private key file (check permissions)")

    def _check_client_ip(self, wireguard_config: AppConfigWireguard) -> None:
        """Validate client IP exists and is valid
        
        Args:
            wireguard_config: WireGuard configuration section
        """
        if wireguard_config.client_ip is None:
            self.errors.append("Client IP is missing from WireGuard configuration")
        # Additional IP validation is handled by Pydantic's built-in validators

    def _check_output_directory_permissions(self, output_config: AppConfigOutput) -> None:
        """Validate output directory exists and is writable
        
        Args:
            output_config: Output configuration section
        """
        config_dir = Path(output_config.config_dir)
        # Path existence is already validated by Pydantic DirectoryPath
        # We only need to check write permissions
        if not self._is_writable(config_dir):
            self.errors.append(f"Output directory is not writable: {config_dir}")

    def _check_database_existence(self, database_config: AppConfigDatabase) -> None:
        """Check database exists and is accessible
        
        Args:
            database_config: Database configuration section
        """
        db_path = Path(database_config.path)
        if not db_path.exists():
            self.warnings.append(f"Database not found at: {db_path}")
            self.warnings.append("Run database update to create the database")

    @staticmethod
    def _is_writable(path: Path) -> bool:
        """Check if path is writable
        
        Args:
            path: Path to check
            
        Returns:
            bool: True if path is writable, False otherwise
        """
        try:
            test_file = path / '.write_test'
            test_file.touch()
            test_file.unlink()
            return True
        except (OSError, PermissionError):
            return False
