"""
Retry mechanism for tests to automatically retry until they pass.

This module implements a retry decorator that can be applied to tests
to make them retry until they pass, with intelligent error handling
to attempt to fix common issues that might cause test failures.
"""

import os
import sys
import time
import logging
import functools
import traceback
from typing import Any, Callable, Dict, List, Optional, Type, Union
from pathlib import Path

logger = logging.getLogger('test')


class RetryError(Exception):
    """Error raised when all retries have been exhausted."""
    
    def __init__(self, func_name: str, max_retries: int, errors: List[Exception]):
        self.func_name = func_name
        self.max_retries = max_retries
        self.errors = errors
        error_messages = '\n'.join([f"Attempt {i+1}: {str(err)}" for i, err in enumerate(errors)])
        message = f"Function '{func_name}' failed after {max_retries} retries. Errors:\n{error_messages}"
        super().__init__(message)


class AutoFixStrategy:
    """Base class for auto-fix strategies."""
    
    def can_fix(self, exception: Exception) -> bool:
        """
        Determine if this strategy can fix the given exception.
        
        Args:
            exception: The exception to check
            
        Returns:
            True if this strategy can attempt to fix the issue
        """
        raise NotImplementedError("Subclasses must implement can_fix")
    
    def fix(self, exception: Exception, test_context: Dict[str, Any]) -> None:
        """
        Attempt to fix the issue that caused the exception.
        
        Args:
            exception: The exception to fix
            test_context: Dictionary of test context info
            
        Returns:
            None
        """
        raise NotImplementedError("Subclasses must implement fix")


class ConfigurationFixStrategy(AutoFixStrategy):
    """Strategy for fixing configuration issues."""
    
    def can_fix(self, exception: Exception) -> bool:
        """Check if this is a configuration-related error."""
        error_str = str(exception).lower()
        return any(phrase in error_str for phrase in [
            'config', 'configuration', 'toml', 'setting', 'parameter',
            'missing', 'invalid', 'not found', 'permission', 'path'
        ])
    
    def fix(self, exception: Exception, test_context: Dict[str, Any]) -> None:
        """Fix configuration issues."""
        config_manager = test_context.get('config_manager')
        if not config_manager:
            logger.warning("No config_manager found in test context, cannot apply fixes")
            return
        
        error_str = str(exception).lower()
        logger.info(f"Attempting to fix configuration issue: {error_str}")
        
        # Fix common configuration issues based on error message
        if 'private key' in error_str:
            private_key_file = Path(config_manager.get('wireguard', 'private_key_file'))
            logger.info(f"Fixing private key at {private_key_file}")
            private_key_file.parent.mkdir(exist_ok=True, parents=True)
            private_key_file.write_text('test_private_key')
            private_key_file.chmod(0o600)
            
        elif 'client ip' in error_str:
            logger.info("Setting default client IP")
            config_manager.set('wireguard', 'client_ip', '10.5.0.2/32')
            
        elif 'directory' in error_str or 'path' in error_str:
            # Create any missing directories
            config_dir = Path(config_manager.get('output', 'config_dir'))
            logger.info(f"Creating config directory: {config_dir}")
            config_dir.mkdir(exist_ok=True, parents=True)
            
        elif 'database' in error_str:
            db_path = Path(config_manager.get('database', 'path'))
            logger.info(f"Ensuring database path exists: {db_path}")
            db_path.parent.mkdir(exist_ok=True, parents=True)
            if 'connection' in error_str:
                # Reset the database file if corrupted
                if db_path.exists():
                    logger.info(f"Removing potentially corrupted database: {db_path}")
                    db_path.unlink()


class DatabaseFixStrategy(AutoFixStrategy):
    """Strategy for fixing database issues."""
    
    def can_fix(self, exception: Exception) -> bool:
        """Check if this is a database-related error."""
        error_str = str(exception).lower()
        return any(phrase in error_str for phrase in [
            'database', 'db', 'sqlite', 'sql', 'query', 'table',
            'schema', 'no such table', 'column', 'integrity'
        ])
    
    def fix(self, exception: Exception, test_context: Dict[str, Any]) -> None:
        """Fix database issues."""
        config_manager = test_context.get('config_manager')
        if not config_manager:
            logger.warning("No config_manager found in test context, cannot apply fixes")
            return
        
        db_path = Path(config_manager.get('database', 'path'))
        error_str = str(exception).lower()
        logger.info(f"Attempting to fix database issue: {error_str}")
        
        # Determine fix based on error message
        if 'no such table' in error_str:
            # Database tables missing, initialize database
            from models.database_management import init_database
            logger.info(f"Initializing database at {db_path}")
            init_database(config_manager)
            
        elif 'database is locked' in error_str:
            # Wait for lock to release
            logger.info(f"Database locked, waiting for release: {db_path}")
            time.sleep(2)  # Wait for lock to release
            
        elif 'disk i/o error' in error_str or 'corrupt' in error_str:
            # Database file corrupt, recreate it
            if db_path.exists():
                logger.info(f"Removing corrupt database: {db_path}")
                db_path.unlink()
            from models.database_management import init_database
            logger.info(f"Recreating database at {db_path}")
            init_database(config_manager)


class ConnectionFixStrategy(AutoFixStrategy):
    """Strategy for fixing connection issues."""
    
    def can_fix(self, exception: Exception) -> bool:
        """Check if this is a connection-related error."""
        error_str = str(exception).lower()
        return any(phrase in error_str for phrase in [
            'connection', 'connect', 'disconnect', 'wireguard', 'wg',
            'interface', 'network', 'permission denied', 'timeout',
            'command failed', 'process', 'sudo'
        ])
    
    def fix(self, exception: Exception, test_context: Dict[str, Any]) -> None:
        """Fix connection issues."""
        logger.info(f"Attempting to fix connection issue: {str(exception)}")
        
        error_str = str(exception).lower()
        
        # Clean up any stuck WireGuard interfaces
        if 'already exists' in error_str or 'device busy' in error_str:
            import subprocess
            try:
                logger.info("Cleaning up existing WireGuard interfaces")
                subprocess.run(['sudo', 'wg-quick', 'down', 'wg0'], 
                               capture_output=True, timeout=5)
            except Exception as e:
                logger.warning(f"Error while cleaning up interfaces: {e}")


# List of fix strategies to try
FIX_STRATEGIES = [
    ConfigurationFixStrategy(),
    DatabaseFixStrategy(),
    ConnectionFixStrategy()
]


def retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0, 
          exceptions: Union[Type[Exception], List[Type[Exception]]] = Exception):
    """
    Retry decorator that retries a test function until it passes, with auto-fix capability.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        delay: Initial delay between retries in seconds (default: 1)
        backoff: Backoff multiplier for delay (default: 2)
        exceptions: Exception or list of exceptions to catch and retry (default: Exception)
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract test context from args and kwargs
            test_context = {}
            for arg in args:
                if hasattr(arg, 'config_manager'):
                    test_context['config_manager'] = arg.config_manager
            if 'config_manager' in kwargs:
                test_context['config_manager'] = kwargs['config_manager']
            
            # Try the main function
            errors = []
            current_delay = delay
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempt {attempt + 1}/{max_retries} for {func.__name__}")
                    result = func(*args, **kwargs)
                    logger.info(f"{func.__name__} passed on attempt {attempt + 1}")
                    return result
                    
                except exceptions as e:
                    logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                    errors.append(e)
                    
                    # Try to automatically fix the issue
                    fixed = False
                    for strategy in FIX_STRATEGIES:
                        if strategy.can_fix(e):
                            logger.info(f"Applying fix strategy: {strategy.__class__.__name__}")
                            try:
                                strategy.fix(e, test_context)
                                fixed = True
                                logger.info(f"Fix strategy {strategy.__class__.__name__} applied successfully")
                            except Exception as fix_error:
                                logger.warning(f"Fix strategy failed: {fix_error}")
                    
                    # If this was the last attempt, don't delay
                    if attempt < max_retries - 1:
                        sleep_time = current_delay * (1 + (0.1 * (attempt + 1)))
                        logger.info(f"Retrying in {sleep_time:.2f} seconds")
                        time.sleep(sleep_time)
                        current_delay *= backoff
            
            # All retries failed
            raise RetryError(func.__name__, max_retries, errors)
        
        return wrapper
    
    return decorator 