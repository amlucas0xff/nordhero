"""
Constants used throughout the NordHero VPN Manager application.

This module centralizes all magic numbers and configuration constants to improve
code maintainability and reduce the likelihood of errors from inconsistent values.
"""

# Network and Protocol Constants
DEFAULT_KEEPALIVE_SECONDS = 25
WIREGUARD_PORT = 51820
DEFAULT_CLIENT_IP = "10.5.0.2/32"
DEFAULT_DNS = "192.168.68.14"

# Server Management Constants
DEFAULT_MAX_LOAD = 100
TOP_SERVERS_LIMIT = 10
DEFAULT_LIMIT = 0  # No limit

# UI and Display Constants
MONITOR_UPDATE_INTERVAL_MS = 900
TERMINAL_MIN_WIDTH = 60
TERMINAL_MIN_HEIGHT = 16

# UI Separator Widths
UI_SEPARATOR_WIDTH_SMALL = 30
UI_SEPARATOR_WIDTH_MEDIUM = 50
UI_SEPARATOR_WIDTH_LARGE = 80

# Column and Layout Constants
COLUMN_WIDTH_DEFAULT = 20
COLUMN_COUNT_COUNTRIES = 3
MAX_OPTION_LENGTH_PADDING = 2

# Validation Constants
WIREGUARD_KEY_LENGTH = 44
WIREGUARD_KEY_SUFFIX = '='

# Progress and Loading Constants
PROGRESS_BAR_TOTAL = 100
PROGRESS_SLEEP_INTERVAL = 0.02  # 20ms for progress bar simulation

# File Permissions
PRIVATE_KEY_PERMISSIONS = 0o600
CONFIG_DIR_PERMISSIONS = 0o700

# Timeout Constants (in seconds)
API_TIMEOUT_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 30
SYSTEMD_WAIT_TIMEOUT = 5

# Database Constants
CSV_BATCH_SIZE = 1000
METADATA_KEY_LAST_UPDATE = 'last_update'

# Curses/Terminal Constants
CURSES_NAPMS_INTERVAL = 1  # 1ms sleep between key checks
SPACE_KEY_CODE = 32  # ord(' ')

# Menu and Input Constants
MENU_CHOICE_RANGE_START = 0
MENU_CHOICE_RANGE_END = 8
INVALID_CHOICE_RETRY_LIMIT = 3

# System Constants
SYSTEMD_SERVICE_NAME = "nordhero-vpn"
SYSTEM_SERVICE_PATH_TEMPLATE = "/etc/systemd/system/{}.service"
USER_SERVICE_DIR = ".config/systemd/user"

# Error Message Constants
ERROR_PREFIX = "✗"
SUCCESS_PREFIX = "✓"
WARNING_PREFIX = "○"