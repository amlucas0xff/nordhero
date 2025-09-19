import pytest
import os
import time
import toml
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, mock_open

from models.config_management import ConfigManager
from models.validator_management import ConfigValidator
from models.data_models import AppConfig

# Import the retry decorator and fix strategies
# In a real test, these would be imported from your actual module
# For the purpose of this test, we'll define them here
def retry(max_attempts=3, delay=0.1, exceptions=(Exception,), log_func=print):
    """Decorator that retries a function on failure with exponential backoff"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempts += 1
                    if attempts == max_attempts:
                        log_func(f"Failed after {attempts} attempts: {e}")
                        raise
                    log_func(f"Attempt {attempts} failed: {e}, retrying after {delay}s")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

class ConfigurationFixStrategy:
    """Strategy to automatically fix configuration issues"""
    def __init__(self, config_manager):
        self.config_manager = config_manager
    
    def attempt_fix(self, exception):
        """Check if we can fix this configuration issue"""
        if isinstance(exception, toml.TomlDecodeError):
            print("Fixing corrupt configuration file...")
            self._recreate_config()
            return True
        
        if isinstance(exception, FileNotFoundError) and "config.toml" in str(exception):
            print("Creating missing configuration file...")
            self._recreate_config()
            return True
            
        return False
    
    def _recreate_config(self):
        """Recreate the configuration from defaults"""
        self.config_manager._create_initial_config()


@pytest.fixture
def retry_config_manager(tmp_path):
    """Create a ConfigManager with retry decorator applied"""
    manager = ConfigManager(tmp_path)
    
    # Patch the load_or_create method with retry decorator
    original_load = manager.load_or_create
    
    # Apply retry decorator
    manager.load_or_create = retry(
        max_attempts=3, 
        delay=0.01,  # Short delay for tests
        exceptions=(Exception,)
    )(original_load)
    
    # Patch the set method with retry decorator
    original_set = manager.set
    
    # Apply retry decorator
    manager.set = retry(
        max_attempts=3, 
        delay=0.01,  # Short delay for tests
        exceptions=(Exception,)
    )(original_set)
    
    return manager

@pytest.fixture
def fix_strategy(retry_config_manager):
    """Create a fix strategy for the config manager"""
    return ConfigurationFixStrategy(retry_config_manager)

def test_load_config_with_retry(retry_config_manager, fix_strategy):
    """Test loading configuration with retry functionality"""
    # Set up the failure scenario
    call_count = 0
    
    # Mock that fails initially but succeeds later
    def mock_exists_with_failures(self):
        nonlocal call_count
        if 'config.toml' in str(self):
            call_count += 1
            if call_count < 2:
                # First attempt fails
                return False
        # All other files exist
        return True
    
    # Create a mock config file content
    mock_config_content = """
    [wireguard]
    private_key_file = "config/wireguard.key"
    client_ip = "10.5.0.2/32"
    dns = "192.168.68.14"
    persistent_keepalive = 25
    
    [database]
    path = "servers.db"
    max_load = 100
    default_limit = 0
    
    [output]
    config_dir = "/etc/wireguard"
    config_wg_file = "/etc/wireguard/wg0.conf"
    """
    
    # Apply the mocks
    with patch('pathlib.Path.exists', mock_exists_with_failures), \
         patch.object(retry_config_manager, '_create_initial_config') as mock_create_config, \
         patch.object(fix_strategy, 'attempt_fix', return_value=True), \
         patch('builtins.open', mock_open(read_data=mock_config_content)):
        
        # Make sure _create_initial_config creates the config file
        def side_effect_create_config():
            # After this is called, the config file should exist in subsequent checks
            nonlocal call_count
            call_count = 2  # Force exists to return True on next call
        
        mock_create_config.side_effect = side_effect_create_config
        
        # This should retry and eventually succeed
        try:
            retry_config_manager.load_or_create()
            # Assert we retried the right number of times
            assert call_count >= 2  # At least one failure + one success
        except Exception as e:
            pytest.fail(f"Should not have raised an exception after retries: {e}")

def test_set_config_with_retry(retry_config_manager):
    """Test setting configuration with retry functionality"""
    # Set up the config manager
    config_dir = retry_config_manager.project_root / 'config'
    config_dir.mkdir(exist_ok=True)
    
    # Initialize basic configuration
    retry_config_manager.config = AppConfig.model_validate({
        'wireguard': {
            'private_key_file': str(config_dir / 'wireguard.key'),
            'client_ip': '10.5.0.2/32',
            'dns': '192.168.68.14',
            'persistent_keepalive': 25
        },
        'database': {
            'path': 'servers.db',
            'max_load': 100,
            'default_limit': 0
        },
        'output': {
            'config_dir': '/etc/wireguard',
            'config_wg_file': '/etc/wireguard/wg0.conf'
        }
    })
    
    # Set up the failure scenario
    call_count = 0
    
    # Create a mock that fails initially but succeeds later
    def mock_open_with_failures(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:  # First two attempts fail
            raise PermissionError(f"Simulated error #{call_count}")
        # Third attempt succeeds
        return mock_open()(*args, **kwargs)
    
    # Apply the mock
    with patch('builtins.open', side_effect=mock_open_with_failures):
        # This should retry and eventually succeed
        try:
            # Instead of save(), use set() which will internally save the config
            retry_config_manager.set('wireguard', 'dns', '1.1.1.1')
            # Assert we retried the right number of times
            assert call_count == 3  # Two failures + one success
        except Exception:
            pytest.fail("Should not have raised an exception after retries")

def test_fix_strategy_integration(retry_config_manager, fix_strategy):
    """Test the integration between retry mechanism and fix strategy"""
    # Mock methods to simulate failure and fix
    with patch.object(retry_config_manager, 'load_or_create', 
                     side_effect=[toml.TomlDecodeError("Invalid TOML", "test", 0), None]), \
         patch.object(fix_strategy, 'attempt_fix', return_value=True) as mock_fix:
        
        # Set up a function that uses retry and fix strategy
        @retry(max_attempts=3, delay=0.01)
        def load_with_fix():
            try:
                retry_config_manager.load_or_create()
            except Exception as e:
                if fix_strategy.attempt_fix(e):
                    retry_config_manager.load_or_create()  # Try again after fix
                else:
                    raise  # Re-raise if not fixed
        
        # Call the function - should succeed after fix
        load_with_fix()
        
        # Verify fix strategy was called
        assert mock_fix.called

def test_different_exception_types(retry_config_manager, fix_strategy):
    """Test handling of different exception types with retry and fix strategy"""
    # Set up different exceptions to test
    exceptions = [
        FileNotFoundError("config.toml not found"),
        PermissionError("Permission denied"),
        toml.TomlDecodeError("Invalid TOML", "test", 0),
        ValueError("Invalid configuration value")
    ]
    
    # Test each exception type
    for exception in exceptions:
        # Reset mocks
        fix_mock = MagicMock(return_value=isinstance(exception, (FileNotFoundError, toml.TomlDecodeError)))
        fix_strategy.attempt_fix = fix_mock
        
        # Function that raises the exception and uses fix strategy
        @retry(max_attempts=2, delay=0.01)
        def operation_with_exception():
            try:
                raise exception
            except Exception as e:
                if fix_strategy.attempt_fix(e):
                    return "fixed"
                raise
        
        # Test the function's behavior
        try:
            result = operation_with_exception()
            # Should only succeed for exceptions we can fix
            assert isinstance(exception, (FileNotFoundError, toml.TomlDecodeError))
            assert result == "fixed"
        except Exception as e:
            # Should fail for exceptions we can't fix
            assert isinstance(exception, (PermissionError, ValueError))
            assert isinstance(e, type(exception))
        
        # Verify fix strategy was called
        assert fix_mock.called

def test_multiple_retries_with_eventual_success():
    """Test multiple retries with eventual success"""
    # Counter for tracking attempts
    attempts = 0
    
    # Function that succeeds on the 3rd attempt
    @retry(max_attempts=5, delay=0.01)
    def stubborn_function():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Simulated connection error")
        return "success"
    
    # Call the function
    result = stubborn_function()
    
    # Verify the behavior
    assert result == "success"
    assert attempts == 3  # Failed twice, succeeded on third try

def test_integration_with_validator(retry_config_manager, tmp_path):
    """Test integration between config manager with retry and validator"""
    # Set up the config manager
    config_dir = retry_config_manager.project_root / 'config'
    config_dir.mkdir(exist_ok=True)
    
    # Create key file
    key_file = config_dir / 'wireguard.key'
    key_file.write_text('a' * 43 + '=')  # Valid base64 format
    key_file.chmod(0o600)  # Set proper permissions
    
    # Create a basic configuration
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
    
    # Create config file
    config_file = config_dir / 'config.toml'
    with open(config_file, 'w') as f:
        toml.dump(config, f)
    
    # Set file for the manager
    retry_config_manager.config_file = config_file
    
    # Create validator
    validator = ConfigValidator(retry_config_manager)
    
    # Test validation with retries
    validation_count = 0
    
    # Create a function that initially fails validation
    def mock_validate_all():
        nonlocal validation_count
        validation_count += 1
        if validation_count < 2:
            # On first attempt, make validation fail by mocking a missing key file
            with patch('pathlib.Path.exists', return_value=False):
                return validator.validate_all()
        else:
            # On second attempt, allow validation to succeed
            with patch('pathlib.Path.exists', return_value=True), \
                 patch.object(ConfigValidator, '_is_writable', return_value=True):
                return validator.validate_all()
    
    # Function with retry
    @retry(max_attempts=3, delay=0.01)
    def validate_with_retry():
        result = mock_validate_all()
        if not result.is_valid:
            raise ValueError(f"Validation failed: {result.errors}")
        return result
    
    # Should succeed after retry
    result = validate_with_retry()
    
    # Verify behavior
    assert result.is_valid
    assert validation_count == 2  # One failure + one success 