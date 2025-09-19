import subprocess
import time
import os
import logging
import sys
import pwd
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any

from models.config_management import ConfigManager
from models.data_models import SystemdServiceStatus
from models.helpers import (
    check_file_exists_with_sudo,
    logger,
    handle_keyboard_interrupt
)
from models.ui_helpers import (
    GREEN, RED, YELLOW, RESET, CLEAR_SCREEN,
    safe_input, display_service_status
)
from models.core.container_adapter import get_container_adapter

# System constants
SYSTEMD_SERVICE_NAME = "nordhero-vpn"
SYSTEM_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}.service"
USER_SERVICE_DIR = ".config/systemd/user"

# Systemd service template
SYSTEMD_SERVICE_TEMPLATE = """[Unit]
Description=NordVPN WireGuard VPN Connection
After=network-online.target
Wants=network-online.target
Documentation=https://github.com/amlucas0xff/nordhero

[Service]
Type=oneshot
ExecStart=/usr/bin/wg-quick up {config_path}
ExecStop=/usr/bin/wg-quick down wg0
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


def get_detailed_service_status(user_mode: bool = False) -> str:
    """Get detailed status of systemd service for debugging
    
    Args:
        user_mode: Whether to check user-level service
        
    Returns:
        str: Service status output
    """
    try:
        cmd = ['systemctl']
        if user_mode:
            cmd.extend(['--user'])
        cmd.extend(['status', SYSTEMD_SERVICE_NAME])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"Error getting service status: {e}"
        
def get_service_journal(user_mode: bool = False) -> str:
    """Get service journal logs for better debugging
    
    Args:
        user_mode: Whether to check user-level service
        
    Returns:
        str: Service journal output
    """
    try:
        cmd = ['sudo', 'journalctl']
        if user_mode:
            cmd.extend(['-u', f'user@{os.getuid()}.service', '--grep', SYSTEMD_SERVICE_NAME])
        else:
            cmd.extend(['-u', SYSTEMD_SERVICE_NAME])
        cmd.extend(['-n', '20', '--no-pager'])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"Error getting service journal: {e}"

def check_systemd_available() -> bool:
    """Check if systemd is available on the system
    
    Returns:
        bool: True if systemd is available (always False in containers)
    """
    # Disable systemd functionality in containers
    adapter = get_container_adapter()
    if adapter.environment.is_container:
        return False
        
    try:
        result = subprocess.run(['systemctl', '--version'], 
                              capture_output=True, text=True, timeout=2)
        return result.returncode == 0
    except Exception:
        return False

def _check_service_enabled(user_mode: bool) -> bool:
    """Check if the systemd service is enabled
    
    Args:
        user_mode: Whether to check user-level service
        
    Returns:
        bool: True if service is enabled
    """
    try:
        cmd = ['systemctl']
        if user_mode:
            cmd.extend(['--user'])
        cmd.extend(['is-enabled', SYSTEMD_SERVICE_NAME])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0 and 'enabled' in result.stdout
    except Exception as e:
        logger.warning(f"Failed to check if service is enabled: {e}")
        return False

def _check_service_active(user_mode: bool) -> bool:
    """Check if the systemd service is active
    
    Args:
        user_mode: Whether to check user-level service
        
    Returns:
        bool: True if service is active
    """
    try:
        cmd = ['systemctl']
        if user_mode:
            cmd.extend(['--user'])
        cmd.extend(['is-active', SYSTEMD_SERVICE_NAME])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0 and 'active' in result.stdout
    except Exception as e:
        logger.warning(f"Failed to check if service is active: {e}")
        return False

def check_systemd_status() -> SystemdServiceStatus:
    """Check status of systemd service
    
    Returns:
        SystemdServiceStatus object containing service status information
    """
    # Check user-level service first
    username = pwd.getpwuid(os.getuid())[0]
    user_service_path = f"/home/{username}/{USER_SERVICE_DIR}/{SYSTEMD_SERVICE_NAME}.service"

    # Check if user mode service exists
    if os.path.exists(user_service_path):
        is_active = _check_service_active(user_mode=True)
        is_enabled = _check_service_enabled(user_mode=True)
        return SystemdServiceStatus(
            exists=True,
            enabled=is_enabled,
            active=is_active,
            user_mode=True,
            path=user_service_path
        )
    
    # Check system level service
    if os.path.exists(SYSTEM_SERVICE_PATH):
        is_active = _check_service_active(user_mode=False)
        is_enabled = _check_service_enabled(user_mode=False)
        return SystemdServiceStatus(
            exists=True,
            enabled=is_enabled,
            active=is_active,
            user_mode=False,
            path=SYSTEM_SERVICE_PATH
        )
    
    # No service exists
    return SystemdServiceStatus(
        exists=False,
        enabled=False,
        active=False,
        user_mode=False,
        path=None
    )

def create_systemd_unit_file(config_path: str, user_mode: bool = True) -> tuple:
    """Create systemd unit file for autostarting WireGuard VPN
    
    Args:
        config_path: Path to the WireGuard configuration file
        user_mode: Whether to create a user-level service (True) or system-level (False)
    
    Returns:
        tuple: (success, message)
    """
    try:
        # First verify the config file exists
        if not check_file_exists_with_sudo(config_path):
            return False, f"Error: WireGuard config file not found at {config_path}"
        
        # Format the service file with the correct path
        service_content = SYSTEMD_SERVICE_TEMPLATE.format(config_path=config_path)
        
        if user_mode:
            # Create user systemd directory if it doesn't exist
            USER_SERVICE_DIR.mkdir(parents=True, exist_ok=True)
            service_path = USER_SERVICE_DIR / SYSTEMD_SERVICE_NAME
            
            # Write service file
            with open(service_path, 'w') as f:
                f.write(service_content)
                
            # Reload systemd daemon
            subprocess.run(['systemctl', '--user', 'daemon-reload'])
            
            return True, f"Created user service at {service_path}"
            
        else:
            # System-level service requires sudo
            service_path = SYSTEM_SERVICE_PATH
            
            # Create temporary file
            tmp_path = Path('/tmp') / SYSTEMD_SERVICE_NAME
            with open(tmp_path, 'w') as f:
                f.write(service_content)
                
            # Copy to system directory with sudo
            result = subprocess.run(['sudo', 'cp', str(tmp_path), str(service_path)], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                return False, f"Failed to create system service: {result.stderr}"
                
            # Remove temporary file
            tmp_path.unlink()
            
            # Reload systemd daemon
            subprocess.run(['sudo', 'systemctl', 'daemon-reload'])
            
            return True, f"Created system service at {service_path}"
            
    except Exception as e:
        logger.error(f"Failed to create systemd unit file: {e}")
        return False, f"Failed to create systemd unit file: {str(e)}"

def _execute_systemd_command(command: str, user_mode: bool = True) -> tuple:
    """Execute a systemd command with consistent error handling
    
    Args:
        command: The systemctl command to execute (enable, disable, start, stop)
        user_mode: Whether to run as user-level service (True) or system-level (False)
        
    Returns:
        tuple: (success, message)
    """
    try:
        if user_mode:
            cmd = ['systemctl', '--user', command, SYSTEMD_SERVICE_NAME]
            result = subprocess.run(cmd, capture_output=True, text=True)
        else:
            cmd = ['sudo', 'systemctl', command, SYSTEMD_SERVICE_NAME]
            result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            # Special handling for 'start' command with detailed errors
            if command == 'start':
                return _handle_start_command_error(result, user_mode)
            return False, f"Failed to {command} service: {result.stderr}"
            
        return True, f"Service {command}d successfully"
        
    except Exception as e:
        logger.error(f"Failed to {command} systemd service: {e}")
        return False, f"Failed to {command} service: {str(e)}"

def _handle_start_command_error(result: subprocess.CompletedProcess, user_mode: bool) -> tuple:
    """Handle detailed error reporting for start command failures
    
    Args:
        result: Failed subprocess result from start command
        user_mode: Whether command was run in user mode
        
    Returns:
        tuple: (False, detailed_error_message)
    """
    # Get detailed error information
    status = get_detailed_service_status(user_mode)
    journal = get_service_journal(user_mode)
    
    error_msg = f"Failed to start service: {result.stderr}"
    
    # Extract the most relevant error message from journal logs
    error_lines = [line for line in journal.split('\n') if 'error' in line.lower() or 'failed' in line.lower()]
    if error_lines:
        error_msg += "\n\nDetailed error information:\n" + "\n".join(error_lines[-3:])  # Last 3 error lines
    
    # Check for specific error patterns
    if '/etc/wireguard/wg0.conf' in journal and 'No such file or directory' in journal:
        error_msg += "\n\nThe WireGuard configuration file was not found. Please generate it first using option 4."
    elif "permission denied" in journal.lower():
        error_msg += "\n\nPermission error detected. The service might need to run with elevated privileges."
    
    return False, error_msg

def enable_systemd_service(user_mode: bool = True) -> tuple:
    """Enable the systemd service
    
    Args:
        user_mode: Whether to enable user-level service (True) or system-level (False)
    
    Returns:
        tuple: (success, message)
    """
    return _execute_systemd_command('enable', user_mode)

def disable_systemd_service(user_mode: bool = True) -> tuple:
    """Disable the systemd service
    
    Args:
        user_mode: Whether to disable user-level service (True) or system-level (False)
    
    Returns:
        tuple: (success, message)
    """
    return _execute_systemd_command('disable', user_mode)

def start_systemd_service(user_mode: bool = True) -> tuple:
    """Start the systemd service
    
    Args:
        user_mode: Whether to start user-level service (True) or system-level (False)
    
    Returns:
        tuple: (success, message)
    """
    return _execute_systemd_command('start', user_mode)

def stop_systemd_service(user_mode: bool = True) -> tuple:
    """Stop the systemd service
    
    Args:
        user_mode: Whether to stop user-level service (True) or system-level (False)
    
    Returns:
        tuple: (success, message)
    """
    return _execute_systemd_command('stop', user_mode)

def _perform_initial_checks(config_manager: ConfigManager) -> Tuple[bool, str, Path]:
    """Perform initial checks needed for autostart
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        Tuple of (success, error_message, config_path)
    """
    # Check systemd availability
    if not check_systemd_available():
        return False, "systemd is not available on this system", Path()
    
    # Check WireGuard config path from config
    config_wg_file = config_manager.get('output', 'config_wg_file')
    if not config_wg_file:
        return False, "WireGuard config file path not specified in configuration", Path()
    
    config_path = Path(config_wg_file)
    if not check_file_exists_with_sudo(str(config_path)):
        return False, f"WireGuard config not found at {config_path}", Path()
    
    return True, "", config_path

# Using display_service_status from ui_helpers

def _toggle_service_enable(status: SystemdServiceStatus) -> None:
    """
    Toggle service enable/disable state
    
    Args:
        status: The SystemdServiceStatus object
    """
    if status.enabled:
        success, msg = disable_systemd_service(status.user_mode)
    else:
        success, msg = enable_systemd_service(status.user_mode)
        
    if success:
        print(f"\n{GREEN}✓ {msg}{RESET}")
    else:
        print(f"\n{RED}✗ {msg}{RESET}")

def _toggle_service_active(status: SystemdServiceStatus) -> None:
    """
    Toggle service active/inactive state
    
    Args:
        status: The SystemdServiceStatus object
    """
    if status.active:
        success, msg = stop_systemd_service(status.user_mode)
    else:
        success, msg = start_systemd_service(status.user_mode)
        
    if success:
        print(f"\n{GREEN}✓ {msg}{RESET}")
    else:
        print(f"\n{RED}✗ {msg}{RESET}")
        if not status.active:  # Only show hint if we were trying to start the service
            print(f"\n{YELLOW}For more details, try running: sudo systemctl status {SYSTEMD_SERVICE_NAME}{RESET}")

def _recreate_service(config_path: Path, user_mode: bool) -> None:
    """
    Recreate the systemd service
    
    Args:
        config_path: Path to the WireGuard configuration file
        user_mode: Whether to create a user-level service
    """
    success, msg = create_systemd_unit_file(str(config_path), user_mode=user_mode)
    if success:
        print(f"\n{GREEN}✓ {msg}{RESET}")
    else:
        print(f"\n{RED}✗ {msg}{RESET}")

def _handle_existing_service_management(status: SystemdServiceStatus, config_path: Path) -> None:
    """
    Handle management of an existing systemd service
    
    Args:
        status: The SystemdServiceStatus object
        config_path: Path to the WireGuard configuration file
    """
    display_service_status(status)
    
    print("\nOptions:")
    if status.enabled:
        print("1. Disable autostart at boot")
    else:
        print("1. Enable autostart at boot")
        
    if status.active:
        print("2. Stop VPN service now")
    else:
        print("2. Start VPN service now")
        
    print("3. Recreate service (system-level)")
    print("4. Recreate service (user-level)")
    print("5. Return to main menu")
    
    choice = safe_input("\nSelect an option (1-5): ").strip()
    
    if choice == '1':
        _toggle_service_enable(status)
    
    elif choice == '2':
        _toggle_service_active(status)
    
    elif choice == '3':
        _recreate_service(config_path, user_mode=False)
    
    elif choice == '4':
        _recreate_service(config_path, user_mode=True)

def _create_service_with_enable_option(config_path: Path, user_mode: bool) -> None:
    """
    Create a new systemd service and optionally enable it
    
    Args:
        config_path: Path to the WireGuard configuration file
        user_mode: Whether to create a user-level service
    """
    success, msg = create_systemd_unit_file(str(config_path), user_mode=user_mode)
    if success:
        print(f"\n{GREEN}✓ {msg}{RESET}")
        print("\nWould you like to enable this service to start at boot?")
        if safe_input("(y/n): ").lower().strip() == 'y':
            success, msg = enable_systemd_service(user_mode=user_mode)
            if success:
                print(f"\n{GREEN}✓ {msg}{RESET}")
            else:
                print(f"\n{RED}✗ {msg}{RESET}")
    else:
        print(f"\n{RED}✗ {msg}{RESET}")

def _handle_new_service_creation(config_path: Path) -> None:
    """
    Handle creation of a new systemd service
    
    Args:
        config_path: Path to the WireGuard configuration file
    """
    print("\nNo autostart service is currently configured.")
    print("\nOptions:")
    print("1. Create system-level service (requires sudo)")
    print("2. Create user-level service")
    print("3. Return to main menu")
    
    choice = safe_input("\nSelect an option (1-3): ").strip()
    
    if choice == '1':
        _create_service_with_enable_option(config_path, user_mode=False)
    
    elif choice == '2':
        _create_service_with_enable_option(config_path, user_mode=True)

def manage_autostart(config_manager: ConfigManager) -> None:
    """Handle configuration of VPN autostart via systemd"""
    # Clear screen and display header
    print(CLEAR_SCREEN)
    print("\nVPN Autostart Configuration")
    print("=" * 50)
    
    # Check if we're running in a container
    adapter = get_container_adapter()
    if adapter.environment.is_container:
        print(f"\n{YELLOW}Container Environment Detected{RESET}")
        print("Systemd autostart is not available in container environments.")
        print("\nFor container autostart, consider:")
        print("1. Setting restart policy in docker-compose.yml (restart: unless-stopped)")
        print("2. Using Docker's --restart=unless-stopped flag")
        print("3. Setting up container orchestration (Docker Swarm, Kubernetes)")
        print("\nIn containers, the application runs as the main process and")
        print("will restart automatically with the container.")
        safe_input("\nPress Enter to return to menu...")
        return
    
    # Perform initial checks (only for host systems)
    success, error_message, config_path = _perform_initial_checks(config_manager)
    if not success:
        print(f"\n{RED}{error_message}{RESET}")
        safe_input("\nPress Enter to return to menu...")
        return
    
    print("=" * 50)
    
    # Check current status
    status = check_systemd_status()
    
    # Handle based on whether service exists
    if status.exists:
        _handle_existing_service_management(status, config_path)
    else:
        _handle_new_service_creation(config_path)
    
    safe_input("\nPress Enter to return to menu...")
