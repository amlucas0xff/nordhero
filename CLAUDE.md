# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Application Overview

Nordhero is a Python-based NordVPN WireGuard manager for Linux systems. It provides a CLI interface for connecting to NordVPN servers using the WireGuard protocol, with features for server selection, connection monitoring, and systemd service management.

## Development Commands

**Install Dependencies (uv):**
```bash
uv sync                       # Install all dependencies (production + dev)
uv sync --frozen              # Install from lockfile only
uv add <package>              # Add production dependency
uv add --group dev <package>  # Add development dependency
```

**Run Application:**
```bash
uv run python main.py --setup-config  # Initial setup
uv run python main.py                # Interactive menu
```

**Run Tests:**
```bash
uv run pytest                        # Run all tests
uv run pytest tests/test_config.py   # Run specific test file
uv run pytest -v                     # Verbose output
uv run pytest --cov                  # With coverage
```

**Legacy pip commands (for reference):**
```bash
pip install -r requirements.txt  # Use 'uv sync' instead
python main.py                   # Use 'uv run python main.py' instead
pytest                          # Use 'uv run pytest' instead
```

## Architecture

### Entry Point
- @main.py:173-205 - Main application entry point with signal handling
- @main.py:284-305 - Action handlers for menu options

### Core Components

**Configuration Management**
- @models/config_management.py:11-75 - `ConfigManager` class handles TOML-based configuration
- @models/data_models.py:60-83 - Pydantic models (`AppConfig`, `AppConfigWireguard`, `AppConfigDatabase`, `AppConfigOutput`)
- Manages WireGuard private keys and client settings with validation
- Uses `pathlib` for cross-platform path handling

**Database Management**
- @models/database_management.py - `DatabaseClient` provides SQLite database operations
- Context manager pattern for connection handling
- Stores NordVPN server data locally with metadata tracking
- Includes retry mechanisms and error handling
- Helper functions for consistent query building:
  - `_build_where_clause()` - Build WHERE clause from filters dictionary
  - `_add_load_filter()` - Add load-specific filtering with custom operators

**API Integration**
- @api/nordvpn_client/ - `WireGuardClient` interfaces with NordVPN API
- Fetches server recommendations with filtering
- Handles authentication and rate limiting
- Exports data to CSV format for database import

**Connection Management**
- @models/connection_management.py - WireGuard interface management (wg-quick commands)
- Real-time connection monitoring with curses UI
- Server selection and configuration generation

**WireGuard Configuration**
- @models/wireguard_config.py:6-41 - `WireGuardConfig` dataclass for config generation
- Template-based config file generation
- Integration with server data and user settings

**User Interface Helpers**
- @models/ui_helpers.py - UI utility functions and formatting
- Color-coded status messages and progress indicators
- Terminal-based interaction helpers

**Validation and Error Handling**
- @models/validator_management.py - Comprehensive validation logic
- System dependency checks (WireGuard binaries, systemd)
- Graceful degradation for missing dependencies

**Service Management**
- @models/service_management.py - Systemd service integration
- Autostart configuration and management
- User and system-level service support
- Helper functions for consistent systemd command execution:
  - `_execute_systemd_command()` - Common systemctl execution with error handling
  - `_handle_start_command_error()` - Detailed error reporting for start failures

**Monitoring and Statistics**
- @models/monitor_management.py - Real-time connection monitoring
- Curses-based UI for live status updates
- Data transfer statistics and connection health

**Helper Utilities**
- @models/helpers.py - Common utility functions
- Time formatting, file operations, and system interactions

### Data Flow

1. **Setup**: @models/config_management.py - `ConfigManager` creates TOML config and private key files
2. **Server Discovery**: @api/nordvpn_client/ - `WireGuardClient` fetches servers → @models/database_management.py - `DatabaseClient` stores locally  
3. **Selection**: User selects server → @models/wireguard_config.py - WireGuard config generated
4. **Connection**: `wg-quick` commands manage VPN connection
5. **Monitoring**: @models/monitor_management.py - Real-time status updates via `wg show` parsing

### Application Flow
Detailed workflows documented in @docs/app-flow.md:
- Initial setup and configuration flow
- Server database update flow  
- VPN server selection flow
- Connection management flow
- Real-time monitoring flow
- Autostart configuration flow

## Key Patterns

**Pydantic Data Models**
- @models/data_models.py - All configuration uses typed models for validation
- Type safety with `IPvAnyNetwork`, `IPvAnyAddress`, and custom validators
- Easy serialization to/from TOML and JSON formats

**Error Handling**
- @models/validator_management.py - Comprehensive validation pipeline
- Graceful degradation for system dependencies
- User-friendly error messages with color coding
- Exception handling with detailed logging

**Context Managers**
- @models/database_management.py - Database connections use context managers
- Automatic resource cleanup and transaction management
- Thread-safe database operations

**Dependency Injection**
- Configuration passed through all components
- Testable architecture with mocked dependencies
- Clear separation of concerns

## Testing

**Test Structure:**
- @tests/conftest.py:36-68 - Shared fixtures and configuration with temporary directories
- @tests/test_config.py - Configuration validation tests
- @tests/test_database.py - Database operations integration tests
- @tests/test_server_updater.py - Server update and API integration tests
- @tests/test_retry.py - Retry mechanism tests
- @tests/test_config_integration.py - End-to-end configuration tests

**Key Fixtures:**
- `config_manager(temp_dir)` - Isolated ConfigManager instance with temporary config
- `mock_subprocess()` - Mock system commands (wg, systemctl)
- `mock_wg_client()` - Mock NordVPN API calls with test data

**Testing Patterns:**
- @tests/test_framework_demo.py - Demonstration of testing patterns
- @tests/test_assertions.py - Custom assertion helpers
- @tests/test_base.py - Base test classes and utilities
- Comprehensive mocking of system dependencies
- Temporary directories for isolated test environments
- Error injection for resilience testing

**Test Categories:**
- Integration tests for database operations
- Configuration validation and serialization tests
- Connection management unit tests
- Retry mechanism and error handling tests
- API client mocking and data processing tests

## Security Considerations

**Private Key Management:**
- Private keys stored with 600 permissions in @models/config_management.py
- Automatic key generation if missing
- No credentials hardcoded in source code
- Secure file path handling with `pathlib`

**Sudo Operations:**
- @models/connection_management.py - Sudo operations clearly isolated and validated
- WireGuard interface management requires elevated privileges
- Systemd service operations properly secured

**Input Validation:**
- @models/validator_management.py - All user inputs validated through Pydantic models
- Network address validation for IP ranges
- File path sanitization and existence checks

## System Dependencies

**Required Binaries:**
- `wg` and `wg-quick` - WireGuard protocol implementation
- `systemctl` - systemd service management
- `sudo` - Elevated privilege operations

**Python Dependencies (managed by uv):**
- `pydantic` - Data validation and serialization
- `python-dotenv` - Environment variable loading
- `requests` - HTTP client for NordVPN API
- `toml` - Configuration file parsing
- `tqdm` - Progress bars for operations
- `pytest` (dev) - Testing framework
- `pytest-cov` (dev) - Test coverage reporting

## File Structure

**Core Application:**
- @main.py - Application entry point and menu system
- @models/ - Core business logic modules
- @api/ - External API clients and integrations
- @config/ - Configuration files and private keys

**Testing and Documentation:**
- @tests/ - Comprehensive test suite with fixtures
- @docs/ - Application flow documentation and diagrams
- @docs/app-flow.md - Detailed workflow documentation

**Configuration Files:**
- `config/config.toml` - Main application configuration
- `config/wireguard.key` - WireGuard private key (600 permissions)
- `servers.db` - Local SQLite database for server data

**Build and Dependencies:**
- `pyproject.toml` - Modern Python project configuration with dependencies
- `uv.lock` - Lockfile for reproducible dependency installations
- `requirements.txt` - Legacy dependency file (kept for compatibility)
- `.gitignore` - Version control exclusions

**Ignored Directories:**
- `sqlmap-dev/` - Separate security testing tool (ignore for main development)

## Development Guidelines

**Code Quality:**
- Follow existing patterns in @models/ for new components
- Use Pydantic models for all data validation
- Implement proper error handling and logging
- Add comprehensive test coverage for new features

**Testing Requirements:**
- Add tests to appropriate files in @tests/
- Use existing fixtures from @tests/conftest.py
- Mock external dependencies (API calls, system commands)
- Test error conditions and edge cases

**Documentation:**
- Update @docs/app-flow.md for new workflows
- Add docstrings following existing patterns
- Document configuration changes in this file