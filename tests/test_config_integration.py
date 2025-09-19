import pytest
import os
from pathlib import Path
import toml
from models.config_management import ConfigManager
from models.validator_management import ConfigValidator, ValidationResult
from models.data_models import AppConfig
from unittest.mock import patch, mock_open, MagicMock

@pytest.fixture
def integrated_config(tmp_path):
    """Create a ConfigManager with integrated validator for testing"""
    # Set up the config manager with a temporary directory
    config_manager = ConfigManager(tmp_path)
    
    # Create the config directory
    config_dir = tmp_path / 'config'
    config_dir.mkdir(exist_ok=True)
    
    # Create private key file
    key_file = config_dir / 'wireguard.key'
    key_file.write_text('a' * 43 + '=')  # Valid base64 format
    key_file.chmod(0o600)  # Set proper permissions
    
    # Create a basic config.toml file
    config = {
        'wireguard': {
            'private_key_file': str(key_file),
            'client_ip': '10.5.0.2/32',
            'dns': '192.168.68.14',
            'persistent_keepalive': 25
        },
        'database': {
            'path': str(tmp_path / 'test_servers.db'),
            'max_load': 100,
            'default_limit': 0
        },
        'output': {
            'config_dir': str(tmp_path / 'wireguard'),
            'config_wg_file': str(tmp_path / 'wireguard/wg0.conf')
        }
    }
    
    # Write the config file
    config_file = config_dir / 'config.toml'
    with open(config_file, 'w') as f:
        toml.dump(config, f)
    
    # Make the output directory
    output_dir = tmp_path / 'wireguard'
    output_dir.mkdir(exist_ok=True)
    
    # Create an empty database file
    db_file = tmp_path / 'test_servers.db'
    db_file.touch()
    
    # Load the configuration
    config_manager.config_file = config_file
    config_manager.load_or_create()
    
    # Create the validator
    validator = ConfigValidator(config_manager)
    
    return {
        'manager': config_manager,
        'validator': validator,
        'tmp_path': tmp_path
    }

def test_integration_valid_config(integrated_config):
    """Test validation of a valid configuration"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    
    # Validate the configuration
    result = validator.validate_all()
    
    # Check validation succeeded
    assert result.is_valid
    assert len(result.errors) == 0
    assert len(result.warnings) == 0
    
    # Check key values were loaded properly
    assert str(manager.config.wireguard.client_ip) == '10.5.0.2/32'
    assert manager.config.database.max_load == 100
    assert 'wireguard/wg0.conf' in str(manager.config.output.config_wg_file)

def test_integration_missing_key_file(integrated_config):
    """Test validation when the private key file is missing"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    tmp_path = integrated_config['tmp_path']
    
    # Delete the key file
    key_file = Path(manager.config.wireguard.private_key_file)
    key_file.unlink()
    
    # Validate the configuration
    result = validator.validate_all()
    
    # Check validation failed
    assert not result.is_valid
    assert any("missing" in err.lower() for err in result.errors)

def test_integration_invalid_private_key(integrated_config):
    """Test validation with an invalid private key"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    
    # Corrupt the private key
    key_file = Path(manager.config.wireguard.private_key_file)
    key_file.write_text('invalid_key_format')
    
    # Validate the configuration
    result = validator.validate_all()
    
    # Check validation failed
    assert not result.is_valid
    assert any("invalid" in err.lower() for err in result.errors)

def test_integration_output_dir_permissions(integrated_config):
    """Test validation with output directory permission issues"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    
    # Mock the is_writable check to simulate permission issues
    with patch.object(ConfigValidator, '_is_writable', return_value=False):
        # Validate the configuration
        result = validator.validate_all()
        
        # Check validation failed with permission error
        assert not result.is_valid
        assert any("not writable" in err.lower() for err in result.errors)

def test_integration_fix_invalid_config(integrated_config):
    """Test fixing an invalid configuration and re-validating"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    tmp_path = integrated_config['tmp_path']
    
    # Attempt to set an invalid IP, but catch the validation error
    try:
        # This will raise a validation error since 999.999.999.999 is not a valid IP
        manager.set('wireguard', 'client_ip', '999.999.999.999')
    except Exception:
        # Expected validation error, proceed with test
        pass
    
    # Set a valid IP instead
    manager.set('wireguard', 'client_ip', '10.5.0.3/32')
    
    # Validate the configuration
    result = validator.validate_all()
    
    # Should pass validation
    assert result.is_valid
    assert str(manager.config.wireguard.client_ip) == '10.5.0.3/32'

def test_integration_missing_database(integrated_config):
    """Test validation with missing database file"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    
    # Get db path for comparison
    db_path = str(manager.config.database.path)
    
    # Set up mocking to make only the database file not exist
    original_exists = Path.exists
    
    def mock_exists(self):
        # Return False specifically for the database path
        if str(self) == db_path:
            return False
        # Otherwise use the original behavior
        return True
    
    with patch('pathlib.Path.exists', mock_exists):
        # Validate with mock
        result = validator.validate_all()
        
        # Should still be valid but with warnings
        assert result.is_valid  # Missing DB should not fail validation
        assert len(result.warnings) > 0

def test_integration_runtime_config_change(integrated_config):
    """Test changing configuration at runtime and validating"""
    manager = integrated_config['manager']
    validator = integrated_config['validator']
    
    # Initial validation should pass
    result = validator.validate_all()
    assert result.is_valid
    
    # Change configuration values
    manager.set('wireguard', 'dns', '1.1.1.1')
    
    # Re-validate with changed config
    result = validator.validate_all()
    assert result.is_valid
    
    # Verify the change took effect
    assert str(manager.config.wireguard.dns) == '1.1.1.1'

def test_integration_auto_retry_decorator():
    """Test the auto-retry decorator with configuration operations"""
    # This test would normally use the @retry decorator from test_retry.py
    # For demonstration, we'll create a mock retry decorator
    
    def mock_retry(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < 3:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == 3:
                        raise
            return None
        return wrapper
    
    # Apply our mock decorator to a test function
    @mock_retry
    def load_config_with_retry(manager):
        if not hasattr(load_config_with_retry, 'attempts'):
            load_config_with_retry.attempts = 0
        
        load_config_with_retry.attempts += 1
        if load_config_with_retry.attempts < 3:
            raise ValueError("Simulated error")
        return "Success"
    
    # Test the function with retries
    result = load_config_with_retry(None)
    assert result == "Success"
    assert load_config_with_retry.attempts == 3 