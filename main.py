import sys
from pathlib import Path
import logging
import argparse
from typing import List, Dict, Optional, Callable, Any, Tuple, Union
from models.config_management import ConfigManager
from models.wireguard_config import WireGuardConfig
from models.validator_management import ConfigValidator
from models.core.exceptions import ConfigurationError, ValidationError, DatabaseError
from models.core.constants import UI_SEPARATOR_WIDTH_SMALL
import signal
import subprocess
import os
import time
import shutil

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
    get_time_ago,
    DatabaseClient,
    get_best_servers
)
from models.helpers import (
    check_file_exists_with_sudo,
    handle_keyboard_interrupt,
    logger
)
from models.core.container_adapter import get_container_adapter
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
    
    # Setup and help arguments
    parser.add_argument('--setup-config', action='store_true',
                       help='Initial setup to configure WireGuard (required for first use)')
    parser.add_argument('-h', '--help', action='store_true',
                       help='Show this help message and exit')
    
    # VPN operation arguments
    parser.add_argument('--connect', nargs='?', const='auto', metavar='SERVER',
                       help='Connect to VPN (auto selects best server or specify server hostname)')
    parser.add_argument('--disconnect', action='store_true',
                       help='Disconnect from VPN')
    parser.add_argument('--status', action='store_true',
                       help='Show current connection status')
    parser.add_argument('--update-servers', type=int, nargs='?', const=0, metavar='LIMIT',
                       help='Update server database (optionally specify limit, 0 for all)')
    parser.add_argument('--list-servers', nargs='?', const='all', metavar='COUNTRY',
                       help='List available servers (optionally filter by country)')
    
    return parser.parse_known_args()[0]

def _display_help() -> None:
    """Display help message"""
    parser = argparse.ArgumentParser(description='Nordhero - NordVPN WireGuard Manager')
    parser.add_argument('--setup-config', action='store_true',
                       help='Initial setup to configure WireGuard (required for first use)')
    parser.add_argument('--connect', nargs='?', const='auto', metavar='SERVER',
                       help='Connect to VPN (auto selects best server or specify server hostname)')
    parser.add_argument('--disconnect', action='store_true',
                       help='Disconnect from VPN')
    parser.add_argument('--status', action='store_true',
                       help='Show current connection status')
    parser.add_argument('--update-servers', type=int, nargs='?', const=0, metavar='LIMIT',
                       help='Update server database (optionally specify limit, 0 for all)')
    parser.add_argument('--list-servers', nargs='?', const='all', metavar='COUNTRY',
                       help='List available servers (optionally filter by country)')
    
    parser.print_help()
    # Show container-specific or host-specific usage
    adapter = get_container_adapter()
    if adapter.environment.is_container:
        print("\nContainer Usage Examples:")
        print("  docker exec -it nordhero python main.py --status")
        print("  docker exec -it nordhero python main.py --connect")
        print("  docker exec -it nordhero python main.py --disconnect")
        print("  docker exec -it nordhero python main.py --update-servers")
        print("  docker exec -it nordhero python main.py")
        print("\nDocker Compose Usage:")
        print("  docker-compose exec nordhero python main.py --status")
        print("  docker-compose exec nordhero python main.py")
    else:
        print("\nCLI Usage Examples:")
        print("  python main.py --status                    # Check connection status")
        print("  python main.py --connect                   # Connect to best server")
        print("  python main.py --connect us1234.nordvpn.com # Connect to specific server")
        print("  python main.py --disconnect                # Disconnect from VPN")
        print("  python main.py --update-servers            # Update all servers")
        print("  python main.py --update-servers 50         # Update with limit of 50")
        print("  python main.py --list-servers              # List best servers globally")
        print("  python main.py --list-servers 'United States' # List servers in specific country")
    
    print("\nInteractive Mode Options:")
    print("- Make an initial setup to configure WireGuard (required for first use)")
    print("- Create/Update local database with NordVPN servers")
    print("- Choose by criteria and select the best VPN server to be connected via WireGuard")
    print("- Manage connection (connect, disconnect or restart VPN)")
    if not adapter.environment.is_container:
        print("- Manage systemd service to start Nordhero when system starts")
    print("- Monitor connection (automatically updates every 1 second)")
    
    if adapter.environment.is_container:
        print("\nContainer Setup:")
        print("1. Set environment variables:")
        print("   - NORDHERO_PRIVATE_KEY: Your WireGuard private key")
        print("   - NORDHERO_CLIENT_IP: Your client IP (optional)")
        print("2. Or run setup interactively:")
        print("   docker exec -it nordhero python main.py --setup-config")
    else:
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
    print("=" * UI_SEPARATOR_WIDTH_SMALL)
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

def cli_status() -> None:
    """Show connection status and exit"""
    status_report = check_wireguard_status(quiet=True)
    if status_report.is_connected:
        print(f"{GREEN}● Connected{RESET}")
        if status_report.app_server_info:
            server_info = status_report.app_server_info
            print(f"Server: {server_info.country}, {server_info.city} (Load: {server_info.load}%)")
            print(f"Hostname: {server_info.hostname}")
            if server_info.endpoint:
                print(f"Endpoint: {server_info.endpoint}")
    else:
        print(f"{RED}○ Not Connected{RESET}")

def cli_disconnect() -> None:
    """Disconnect from VPN"""
    try:
        result = subprocess.run(['sudo', 'wg-quick', 'down', 'wg0'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"{GREEN}✓ Disconnected from VPN{RESET}")
        else:
            print(f"{RED}✗ Failed to disconnect: {result.stderr}{RESET}")
    except Exception as e:
        print(f"{RED}✗ Error disconnecting: {e}{RESET}")

def cli_update_servers(limit: int, config_manager: ConfigManager) -> None:
    """Update server database"""
    print(f"\nUpdating server database (limit: {limit if limit > 0 else 'unlimited'})...")
    try:
        new_count, prev_count = init_database(limit, config_manager)
        print(f"{GREEN}✓ Successfully updated server database{RESET}")
        print(f"Servers: {prev_count} → {new_count}")
    except Exception as e:
        print(f"{RED}✗ Failed to update servers: {e}{RESET}")

def cli_list_servers(country: Optional[str], config_manager: ConfigManager) -> None:
    """List available servers"""
    country_filter = None if country == 'all' else country
    try:
        db_path = config_manager.get('database', 'path', 'servers.db')
        servers = get_best_servers(country=country_filter, limit=10, db_path=db_path)
        if servers:
            print(f"\nTop servers{f' in {country}' if country_filter else ' globally'}:")
            print("-" * 70)
            print(f"{'Hostname':<30} {'Country':<20} {'City':<15} {'Load':<5}")
            print("-" * 70)
            for server in servers:
                print(f"{server.hostname:<30} {server.country:<20} {server.city:<15} {server.load}%")
        else:
            print(f"{RED}No servers found{f' in {country}' if country_filter else ''}{RESET}")
    except Exception as e:
        print(f"{RED}✗ Failed to list servers: {e}{RESET}")

def cli_connect(server_arg: str, config_manager: ConfigManager) -> None:
    """Connect to VPN server"""
    try:
        if server_arg == 'auto':
            # Auto-select best server
            db_path = config_manager.get('database', 'path', 'servers.db')
            servers = get_best_servers(limit=1, db_path=db_path)
            if not servers:
                print(f"{RED}✗ No servers available. Update server list first.{RESET}")
                return
            server = servers[0]
            print(f"Auto-selected: {server.hostname} ({server.country}, {server.city})")
        else:
            # Connect to specific server by hostname
            db_path = config_manager.get('database', 'path', 'servers.db')
            with DatabaseClient(db_path=db_path) as db:
                servers = db.get_servers(hostname=server_arg, limit=1)
                if not servers:
                    print(f"{RED}✗ Server '{server_arg}' not found{RESET}")
                    return
                server = servers[0]
        
        # Generate config and connect
        config_content = generate_wireguard_config(server, config_manager)
        config_path = Path(config_manager.get('output', 'config_wg_file'))
        
        # Write config with sudo
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp_file:
            tmp_file.write(config_content)
            tmp_path = tmp_file.name
        
        # Copy to final location and connect
        subprocess.run(['sudo', 'cp', tmp_path, str(config_path)], check=True)
        Path(tmp_path).unlink()  # Clean up temp file
        
        result = subprocess.run(['sudo', 'wg-quick', 'up', str(config_path)], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"{GREEN}✓ Connected to {server.hostname}{RESET}")
        else:
            print(f"{RED}✗ Failed to connect: {result.stderr}{RESET}")
            
    except Exception as e:
        print(f"{RED}✗ Error connecting: {e}{RESET}")

def handle_cli_actions(args: argparse.Namespace, config_manager: ConfigManager) -> bool:
    """Simple dispatcher for CLI actions"""
    if args.status:
        cli_status()
        return True
    elif args.disconnect:
        cli_disconnect()
        return True
    elif args.update_servers is not None:
        cli_update_servers(args.update_servers, config_manager)
        return True
    elif args.list_servers is not None:
        cli_list_servers(args.list_servers, config_manager)
        return True
    elif args.connect is not None:
        cli_connect(args.connect, config_manager)
        return True
    return False  # No CLI action

def main() -> None:
    """Main entry point"""
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    
    try:
        # Parse arguments
        args = _parse_arguments()
        
        # Initialize configuration with container awareness
        adapter = get_container_adapter()
        if adapter.environment.is_container:
            # In container mode, use /app as the project root
            config_manager = ConfigManager(Path('/app'))
        else:
            # Host mode - use existing logic
            config_manager = ConfigManager(Path(__file__).parent)
        
        # Log container environment info for debugging
        if adapter.environment.is_container:
            logger.info(f"Running in container mode: {adapter.environment.container_type}")
            logger.debug(f"Container environment info: {adapter.get_environment_info()}")
        
        # Perform initial checks
        if not _perform_initial_checks(args, config_manager):
            sys.exit(0)
        
        # Handle CLI actions (if any)
        if handle_cli_actions(args, config_manager):
            sys.exit(0)  # CLI action completed
        
        # Otherwise continue to interactive menu
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
    except FileNotFoundError:
        print(f"{RED}✗ Private key file not found{RESET}")
        logger.warning("Private key file is missing")
        return False
    except PermissionError:
        print(f"{RED}✗ Cannot read private key file (permission denied){RESET}")
        logger.warning("Permission denied accessing private key file")
        return False
    except (ConfigurationError, ValidationError) as e:
        print(f"{RED}✗ Private key configuration error: {e.message}{RESET}")
        logger.error(f"Private key configuration error: {e}")
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
    except DatabaseError as e:
        print(f"{RED}  ↳ Database error: Unable to query server count{RESET}")
        logger.error(f"SQLite error checking database status: {e}")
        return False
    except DatabaseError as e:
        print(f"{RED}  ↳ Database connection error: {e.message}{RESET}")
        logger.error(f"Database error checking status: {e}")
        return False
    except Exception as e:
        print(f"{RED}  ↳ Unexpected error accessing database{RESET}")
        logger.error(f"Unexpected error checking database status: {e}")
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
    print("=" * UI_SEPARATOR_WIDTH_SMALL)
    
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
