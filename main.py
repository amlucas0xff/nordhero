import sys
from pathlib import Path
import logging
import argparse
from textwrap import dedent
from typing import List, Dict, Optional, Callable, Any, Tuple, Union
from models.config_management import ConfigManager
from models.wireguard_config import WireGuardConfig
from models.validator_management import ConfigValidator
from datetime import datetime
import signal
from time import sleep
from tqdm import tqdm
import subprocess
import os
import time
import select
import tty
import termios
import shutil
import curses
import pwd

from api.nordvpn_client.wireguard import WireGuardClient
from models.database_management import DatabaseClient
from models.monitor_management import MonitorWindow
from models.connection_management import (
    manage_connection, 
    monitor_connection, 
    check_wireguard_status, 
    update_server_list,
    show_top_servers,
    select_vpn_endpoint,
    select_by_country,
    generate_wireguard_config,
    generate_config_from_list
)
from models.service_management import (
    check_systemd_available,
    check_systemd_status,
    manage_autostart
)
from models.database_management import (
    init_database, 
    check_database_status, 
    get_last_update_time,
    get_time_ago
)
from models.helpers import (
    check_file_exists_with_sudo,
    handle_keyboard_interrupt,
    logger
)
from models.ui_helpers import (
    GREEN, RED, YELLOW, RESET, CLEAR_SCREEN,
    safe_input, display_header, display_server_options
)
from models.data_models import WGStatusReport


def check_wireguard_binaries() -> bool:
    """Check if required WireGuard binaries are installed"""
    missing_binaries = []
    for binary in ['wg', 'wg-quick']:
        if not shutil.which(binary):
            missing_binaries.append(binary)
    
    if missing_binaries:
        print(f"\n{RED}Error: Required WireGuard binaries not found: {', '.join(missing_binaries)}{RESET}")
        print("\nPlease install WireGuard using your distribution's package manager.")
        print("\nFor example:")
        print("  - Debian/Ubuntu: sudo apt install wireguard")
        print("  - Fedora: sudo dnf install wireguard-tools")
        print("  - Arch Linux: sudo pacman -S wireguard-tools")
        print("  - macOS: brew install wireguard-tools")
        return False
    
    return True

def _parse_arguments() -> argparse.Namespace:
    """Parse command line arguments
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Nordhero - NordVPN WireGuard Manager',
        add_help=False
    )
    
    # Add setup-config argument
    parser.add_argument('--setup-config', action='store_true',
                       help='Initial setup to configure WireGuard (required for first use)')
    parser.add_argument('-h', '--help', action='store_true',
                       help='Show this help message and exit')
    
    return parser.parse_known_args()[0]

def _display_help() -> None:
    """Display help message"""
    parser = argparse.ArgumentParser(description='Nordhero - NordVPN WireGuard Manager')
    parser.add_argument('--setup-config', action='store_true',
                       help='Initial setup to configure WireGuard (required for first use)')
    
    parser.print_help()
    print("\nInteractive Mode Options:")
    print("- Make an initial setup to configure WireGuard (required for first use)")
    print("- Create/Update local database with NordVPN servers")
    print("- Choose by criteria and select the best VPN server to be connected via WireGuard")
    print("- Manage connection (connect, disconnect or restart VPN)")
    print("- Manage systemd service to start Nordhero when system starts")
    print("- Monitor connection (automatically updates every 1 second)")
    print("\nBefore using this script:")
    print("1. You need a NordVPN account and an active subscription")
    print("2. Generate your WireGuard private key at:")
    print("   https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/")
    print("\nRun without arguments to access interactive menu")

def _perform_setup(config_manager: ConfigManager) -> None:
    """Perform initial setup
    
    Args:
        config_manager: ConfigManager instance
    """
    if config_manager.config_file.exists():
        print("\nSetup already completed!")
        print("You can manage your connection using the interactive menu")
        return
            
    print("Setup required")
    print("=" * 30)
    print("Let's get your WireGuard configuration set up!")
    config_manager.load_or_create()
    print("\nSetup complete! You can now manage your VPN connection.")
    print("Run 'python main.py' to access the interactive menu")

def _check_initial_setup(config_manager: ConfigManager) -> bool:
    """Check if initial setup is needed
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        True if setup exists, False if setup is needed
    """
    if not config_manager.config_file.exists():
        print("\nWelcome to Nordhero!")
        print("It looks like you need to complete the initial setup.")
        print("Please run: python main.py --setup-config")
        return False
    return True

def _perform_initial_checks(args: argparse.Namespace, config_manager: ConfigManager) -> bool:
    """Perform initial checks and setup
    
    Args:
        args: Parsed command line arguments
        config_manager: ConfigManager instance
        
    Returns:
        True if checks passed, False if program should exit
    """
    # Check for required WireGuard binaries
    if not check_wireguard_binaries():
        return False
    
    # Handle help
    if args.help:
        _display_help()
        return False
        
    # Handle setup-config
    if args.setup_config:
        _perform_setup(config_manager)
        return False
        
    # Check if setup is needed
    if not _check_initial_setup(config_manager):
        return False
    
    # Load configuration
    config_manager.load_or_create()
    return True

def main() -> None:
    """Main entry point"""
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    
    try:
        # Parse arguments
        args = _parse_arguments()
        
        # Initialize configuration
        config_manager = ConfigManager(Path(__file__).parent)
        
        # Perform initial checks
        if not _perform_initial_checks(args, config_manager):
            sys.exit(0)
        
        # Start main menu
        main_menu(config_manager)
        
    except KeyboardInterrupt:
        handle_keyboard_interrupt(None, None)

def _action_check_setup(config_manager: ConfigManager) -> None:
    """Action: Check current setup status
    
    Args:
        config_manager: ConfigManager instance
    """
    check_setup_status(config_manager)

def _action_initial_setup(config_manager: ConfigManager) -> None:
    """Action: Perform initial setup
    
    Args:
        config_manager: ConfigManager instance
    """
    setup_complete = config_manager.config_file.exists()
    database_exists = check_database_status(config_manager)
    
    if setup_complete:
        print(f"\n{GREEN}Setup is already completed!{RESET}")
        if not database_exists:
            print(f"\n{RED}Important:{RESET} Please initialize the local database using Option 2 to continue.")
        else:
            print("\nYou can proceed with using the VPN manager:")
            print("- Use Option 2 to update the local database with NORD VPN servers")
            print("- Use Option 3 to view top servers (with the lowest load)")
            print("- Use Option 4 to select and configure a VPN endpoint to connect to")
        safe_input("\nPress Enter to continue...")
    else:
        config_manager.load_or_create()
        print(f"\n{GREEN}✓ Setup complete!{RESET}")
        print(f"\n{RED}Important:{RESET} Next step is to initialize the database (Option 2)")
        safe_input("\nPress Enter to continue...")

def _action_update_database(config_manager: ConfigManager) -> None:
    """Action: Update server database
    
    Args:
        config_manager: ConfigManager instance
    """
    update_server_list(config_manager)

def _check_database_exists(config_manager: ConfigManager) -> bool:
    """Check if database exists and prompt if not
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        True if database exists, False otherwise
    """
    database_exists = check_database_status(config_manager)
    if not database_exists:
        print(f"\n{RED}Error: Local database is not initialized or does not exist.{RESET}")
        print("Please use Option 2 to make and initialize the local database first.")
        safe_input("\nPress Enter to continue...")
        return False
    return True

def _action_show_top_servers(config_manager: ConfigManager) -> None:
    """Action: Show top 10 global servers
    
    Args:
        config_manager: ConfigManager instance
    """
    if _check_database_exists(config_manager):
        show_top_servers(config_manager)

def _action_select_vpn_endpoint(config_manager: ConfigManager) -> None:
    """Action: Select VPN endpoint
    
    Args:
        config_manager: ConfigManager instance
    """
    if _check_database_exists(config_manager):
        select_vpn_endpoint(config_manager)

def _action_manage_connection(config_manager: ConfigManager) -> None:
    """Action: Manage VPN connection
    
    Args:
        config_manager: ConfigManager instance
    """
    manage_connection(config_manager)

def _action_monitor_connection(config_manager: ConfigManager) -> None:
    """Action: Monitor VPN connection
    
    Args:
        config_manager: ConfigManager instance
    """
    monitor_connection()

def _action_manage_autostart(config_manager: ConfigManager) -> None:
    """Action: Manage Systemd service
    
    Args:
        config_manager: ConfigManager instance
    """
    manage_autostart(config_manager)

def _action_exit(config_manager: ConfigManager) -> None:
    """Action: Exit application
    
    Args:
        config_manager: ConfigManager instance
    """
    print("\nGoodbye!")
    sys.exit(0)

def main_menu(config_manager: ConfigManager) -> None:
    """Display main menu and handle user choices
    
    Args:
        config_manager: ConfigManager instance
    """
    # Create a dispatch dictionary for menu actions
    menu_actions = {
        '0': _action_check_setup,
        '1': _action_initial_setup,
        '2': _action_update_database,
        '3': _action_show_top_servers,
        '4': _action_select_vpn_endpoint, 
        '5': _action_manage_connection,
        '6': _action_monitor_connection,
        '7': _action_manage_autostart,
        '8': _action_exit
    }
    
    while True:
        display_header()
        
        # Check setup and database status
        setup_complete = config_manager.config_file.exists()
        setup_status = f"{GREEN}✓{RESET} " if setup_complete else ""
        database_exists = check_database_status(config_manager)
        
        # Get last update time for display
        last_update = get_last_update_time(config_manager, format_as_time_ago=True)
        update_info = f" (Last update: {last_update})" if last_update != "Never" else " (Not updated yet)"
        
        print("0. Check current setup")
        print(f"1. {setup_status}Initial Setup")
        
        # Show different text for option 2 based on database status
        if database_exists:
            print(f"2. Update database{update_info}")
        else:
            print(f"2. {RED}Initialize database (Required){RESET}")
            
        print("3. Show top 10 global servers")
        print("4. Select vpn endpoint")
        
        # Check current connection status for option 5
        status_report = check_wireguard_status(quiet=True)
        if status_report.is_connected:
            print("5. Manage connection (Disconnect or Restart VPN)")
        else:
            print("5. Connect to VPN previously selected")
            
        print("6. Monitor connection (Automatically updates every 1 second)")
        print("7. Manage systemd service")
        print("8. Exit")
        
        choice = safe_input("\nSelect an option (0-8): ")
        
        # Execute the selected action using the dispatch pattern
        action = menu_actions.get(choice)
        if action:
            action(config_manager)
        else:
            print("Invalid choice. Please try again.")

def _check_config_file_status(config_manager: ConfigManager) -> bool:
    """Check if configuration file exists
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        True if file exists, False otherwise
    """
    if config_manager.config_file.exists():
        print(f"{GREEN}✓ Configuration file exists{RESET}")
        return True
    else:
        print(f"{RED}✗ Configuration file missing{RESET}")
        return False

def _check_private_key_status(config_manager: ConfigManager) -> bool:
    """Check if private key is configured
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        True if key is configured, False otherwise
    """
    try:
        config_manager.get_private_key()
        print(f"{GREEN}✓ Private key configured{RESET}")
        return True
    except Exception:
        print(f"{RED}✗ Private key not configured{RESET}")
        return False

def _check_database_status(config_manager: ConfigManager) -> bool:
    """Check database status with detailed information
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        True if database is valid, False otherwise
    """
    last_update = get_last_update_time(config_manager, format_as_time_ago=True)
    db_path = Path(config_manager.get('database', 'path', 'servers.db'))
    
    if not db_path.exists():
        print(f"{RED}✗ Server database missing{RESET}")
        print(f"{RED}  ↳ Please initialize database using Option 2{RESET}")
        return False
    
    print(f"{GREEN}✓ Server database exists{RESET}")
    print(f"{GREEN}  ↳ Path: {db_path}{RESET}")
    
    # Check if database has servers
    try:
        with DatabaseClient(db_path=db_path) as db:
            db.cursor.execute('SELECT COUNT(*) FROM servers')
            count = db.cursor.fetchone()[0]
            if count > 0:
                print(f"{GREEN}  ↳ Contains {count} servers{RESET}")
                print(f"{GREEN}  ↳ Last update: {last_update}{RESET}")
                return True
            else:
                print(f"{RED}  ↳ Database is empty! Please initialize using Option 2{RESET}")
                return False
    except Exception:
        print(f"{RED}  ↳ Database appears to be corrupted or empty{RESET}")
        return False

def _check_wireguard_config_status(config_manager: ConfigManager) -> bool:
    """Check if WireGuard configuration file exists
    
    Args:
        config_manager: ConfigManager instance
        
    Returns:
        True if config exists, False otherwise
    """
    config_wg_file = config_manager.get('output', 'config_wg_file')
    if not config_wg_file:
        print(f"{RED}✗ WireGuard config path not specified in configuration{RESET}")
        print(f"{RED}  ↳ Please ensure [output] section has config_wg_file in config.toml{RESET}")
        return False
    
    wg_config_path = str(Path(config_wg_file))
    if check_file_exists_with_sudo(wg_config_path):
        print(f"{GREEN}✓ WireGuard config exists{RESET}")
        print(f"{GREEN}  ↳ Path: {wg_config_path}{RESET}")
        return True
    else:
        print(f"{RED}✗ WireGuard config not generated yet{RESET}")
        return False

def check_setup_status(config_manager: ConfigManager) -> None:
    """Check and display current setup status
    
    Args:
        config_manager: ConfigManager instance
    """
    print("\nCurrent Setup Status")
    print("=" * 30)
    
    # Get last update time
    last_update = get_last_update_time(config_manager, format_as_time_ago=True)
    
    # Check each component status
    _check_config_file_status(config_manager)
    _check_private_key_status(config_manager)
    _check_database_status(config_manager)
    _check_wireguard_config_status(config_manager)
    
    print("\n" + "=" * 30)    
    safe_input("\nPress Enter to return to menu...")

if __name__ == "__main__":
    main()
