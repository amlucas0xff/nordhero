"""
Custom exception classes for NordHero VPN Manager.

This module defines specific exception types to replace generic exception handling
throughout the application, providing better error context and debugging information.
"""

from typing import Optional, Any


class NordHeroError(Exception):
    """Base exception class for all NordHero VPN Manager errors."""
    
    def __init__(self, message: str, details: Optional[str] = None, error_code: Optional[str] = None):
        """
        Initialize the base exception.
        
        Args:
            message: Human-readable error message
            details: Additional error details for debugging
            error_code: Machine-readable error code for categorization
        """
        super().__init__(message)
        self.message = message
        self.details = details
        self.error_code = error_code
    
    def __str__(self) -> str:
        """Return a formatted error message."""
        if self.details:
            return f"{self.message}. Details: {self.details}"
        return self.message


class ConfigurationError(NordHeroError):
    """Raised when configuration-related operations fail."""
    
    def __init__(self, message: str, config_path: Optional[str] = None, **kwargs):
        """
        Initialize configuration error.
        
        Args:
            message: Error message
            config_path: Path to the problematic configuration file
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.config_path = config_path


class DatabaseError(NordHeroError):
    """Raised when database operations fail."""
    
    def __init__(self, message: str, db_path: Optional[str] = None, query: Optional[str] = None, **kwargs):
        """
        Initialize database error.
        
        Args:
            message: Error message
            db_path: Path to the database file
            query: SQL query that caused the error (if applicable)
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.db_path = db_path
        self.query = query


class WireGuardError(NordHeroError):
    """Raised when WireGuard operations fail."""
    
    def __init__(self, message: str, interface: Optional[str] = None, command: Optional[str] = None, **kwargs):
        """
        Initialize WireGuard error.
        
        Args:
            message: Error message
            interface: WireGuard interface name (e.g., 'wg0')
            command: WireGuard command that failed
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.interface = interface
        self.command = command


class NetworkError(NordHeroError):
    """Raised when network operations fail."""
    
    def __init__(self, message: str, url: Optional[str] = None, status_code: Optional[int] = None, **kwargs):
        """
        Initialize network error.
        
        Args:
            message: Error message
            url: URL that caused the error
            status_code: HTTP status code (if applicable)
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.url = url
        self.status_code = status_code


class ValidationError(NordHeroError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, field_name: Optional[str] = None, invalid_value: Optional[Any] = None, **kwargs):
        """
        Initialize validation error.
        
        Args:
            message: Error message
            field_name: Name of the field that failed validation
            invalid_value: The value that failed validation
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.field_name = field_name
        self.invalid_value = invalid_value


class SystemdError(NordHeroError):
    """Raised when systemd operations fail."""
    
    def __init__(self, message: str, service_name: Optional[str] = None, operation: Optional[str] = None, **kwargs):
        """
        Initialize systemd error.
        
        Args:
            message: Error message
            service_name: Name of the systemd service
            operation: Systemd operation that failed (e.g., 'start', 'stop', 'enable')
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.service_name = service_name
        self.operation = operation


class UIError(NordHeroError):
    """Raised when user interface operations fail."""
    
    def __init__(self, message: str, ui_component: Optional[str] = None, **kwargs):
        """
        Initialize UI error.
        
        Args:
            message: Error message
            ui_component: UI component that caused the error (e.g., 'menu', 'monitor', 'input')
            **kwargs: Additional arguments passed to base class
        """
        super().__init__(message, **kwargs)
        self.ui_component = ui_component


# Convenience functions for creating common errors

def config_file_not_found(config_path: str) -> ConfigurationError:
    """Create a standardized configuration file not found error."""
    return ConfigurationError(
        f"Configuration file not found: {config_path}",
        config_path=config_path,
        error_code="CONFIG_FILE_NOT_FOUND"
    )


def private_key_invalid(details: str = "Invalid format or length") -> ValidationError:
    """Create a standardized private key validation error."""
    return ValidationError(
        "WireGuard private key is invalid",
        field_name="private_key",
        details=details,
        error_code="PRIVATE_KEY_INVALID"
    )


def database_connection_failed(db_path: str, details: str) -> DatabaseError:
    """Create a standardized database connection error."""
    return DatabaseError(
        f"Failed to connect to database: {db_path}",
        db_path=db_path,
        details=details,
        error_code="DB_CONNECTION_FAILED"
    )


def wireguard_command_failed(command: str, details: str) -> WireGuardError:
    """Create a standardized WireGuard command failure error."""
    return WireGuardError(
        f"WireGuard command failed: {command}",
        command=command,
        details=details,
        error_code="WG_COMMAND_FAILED"
    )


def api_request_failed(url: str, status_code: Optional[int] = None, details: str = "") -> NetworkError:
    """Create a standardized API request failure error."""
    message = f"API request failed: {url}"
    if status_code:
        message += f" (HTTP {status_code})"
    
    return NetworkError(
        message,
        url=url,
        status_code=status_code,
        details=details,
        error_code="API_REQUEST_FAILED"
    )