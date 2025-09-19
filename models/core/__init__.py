"""
Core module containing constants, exceptions, and shared utilities for NordHero VPN Manager.
"""

from .constants import *
from .exceptions import *

__all__ = [
    # Constants
    'DEFAULT_KEEPALIVE_SECONDS',
    'WIREGUARD_PORT',
    'DEFAULT_CLIENT_IP',
    'DEFAULT_DNS',
    'DEFAULT_MAX_LOAD',
    'TOP_SERVERS_LIMIT',
    'MONITOR_UPDATE_INTERVAL_MS',
    'TERMINAL_MIN_WIDTH',
    'TERMINAL_MIN_HEIGHT',
    'UI_SEPARATOR_WIDTH_SMALL',
    'UI_SEPARATOR_WIDTH_MEDIUM',
    'UI_SEPARATOR_WIDTH_LARGE',
    'COLUMN_WIDTH_DEFAULT',
    'WIREGUARD_KEY_LENGTH',
    'PROGRESS_BAR_TOTAL',
    
    # Exceptions
    'NordHeroError',
    'ConfigurationError',
    'DatabaseError',
    'WireGuardError',
    'NetworkError',
    'ValidationError',
    'SystemdError',
    'UIError',
]