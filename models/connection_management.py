import subprocess
import time
from pathlib import Path
import logging
import sys
import curses
import shutil
from typing import Dict, Optional, List, Tuple
from tqdm import tqdm

# Import from the project modules
from models.config_management import ConfigManager
from models.core.exceptions import WireGuardError, DatabaseError, ValidationError, UIError
from models.core.constants import (
    MONITOR_UPDATE_INTERVAL_MS, TOP_SERVERS_LIMIT, DEFAULT_MAX_LOAD,
    UI_SEPARATOR_WIDTH_SMALL, UI_SEPARATOR_WIDTH_MEDIUM
)
from models.monitor_management import MonitorWindow
from models.database_management import init_database, get_last_update_time, DatabaseClient, get_best_servers
from models.wireguard_config import WireGuardConfig
from models.data_models import WGConnectionDetails, WGTransferInfo, ConnectedServerAppInfo, WGStatusReport, ServerDBRecord
from models.ui_helpers import (
    GREEN, RED, YELLOW, RESET, CLEAR_SCREEN,
    safe_input, display_header, display_server_options,
    display_connection_menu_options, prompt_server_selection,
    display_country_selection_ui
)
from models.helpers import (
    check_file_exists_with_sudo,
    logger
)
from models.core.container_adapter import get_container_adapter

def _parse_wg_interface_output(output: str) -> Optional[WGConnectionDetails]:
    """Parse the output of 'sudo wg show <interface>' and return structured connection details
    
    Args:
        output: Output string from wg show command
        
    Returns:
        WGConnectionDetails with parsed information or None if parsing failed
    """
    try:
        connection_info = {
            'public_key': None,
            'endpoint': None,
            'latest_handshake': None,
            'transfer': {'received': '0 B', 'sent': '0 B'}
        }
        
        for line in output.split('\n'):
            line = line.strip().lower()
            if 'peer:' in line:
                connection_info['public_key'] = line.split(':')[1].strip()
            elif 'endpoint:' in line:
                connection_info['endpoint'] = line.split(':')[1].strip()
                if ':' in connection_info['endpoint']:  # If port is included, remove it
                    connection_info['endpoint'] = connection_info['endpoint'].split(':')[0]
            elif 'latest handshake:' in line:
                connection_info['latest_handshake'] = line.split(':', 1)[1].strip()
            elif 'transfer:' in line:
                transfer = line.split(':', 1)[1].strip()
                if 'received' in transfer and 'sent' in transfer:
                    received, sent = transfer.split(',')
                    connection_info['transfer']['received'] = received.split('received')[0].strip()
                    connection_info['transfer']['sent'] = sent.split('sent')[0].strip()
        
        # Create a WGConnectionDetails object from the parsed information
        transfer_info = WGTransferInfo(
            received=connection_info['transfer']['received'],
            sent=connection_info['transfer']['sent']
        )
        
        return WGConnectionDetails(
            public_key=connection_info['public_key'],
            endpoint=connection_info['endpoint'],
            latest_handshake=connection_info['latest_handshake'],
            transfer=transfer_info
        )
    
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing WireGuard interface output - invalid format: {e}")
        return None
    except WireGuardError as e:
        logger.error(f"WireGuard parsing error: {e}")
        return None
    except Exception as e:
        # Only catch truly unexpected errors here
        logger.error(f"Unexpected error parsing WireGuard interface output: {e}")
        return None

def _find_server_in_db(details: WGConnectionDetails, db: DatabaseClient) -> Tuple[Optional[ServerDBRecord], Optional[str]]:
    """Find a server in the database matching the connection details
    
    Args:
        details: Parsed WireGuard connection details
        db: Database client instance
        
    Returns:
        Tuple of (ServerDBRecord or None, method used to find or None)
    """
    method = None
    server = None
    
    try:
        # First try to find server by IP (endpoint)
        if details.endpoint:
            servers = db.get_servers(ip=details.endpoint, limit=1)
            for srv in servers:
                if srv.ip == details.endpoint:
                    server = srv
                    method = 'ip'
                    break
        
        # Fallback to public key if IP not found
        if not server and details.public_key:
            servers = db.get_servers(public_key=details.public_key, limit=1)
            for srv in servers:
                if srv.public_key == details.public_key:
                    server = srv
                    method = 'public_key'
                    break
    
    except DatabaseError as e:
        logger.error(f"Database error finding server: {e}")
    except (ValueError, AttributeError) as e:
        logger.error(f"Data validation error finding server: {e}")
    except Exception as e:
        # Only catch truly unexpected errors here
        logger.error(f"Unexpected error finding server in database: {e}")
    
    return server, method

def check_wireguard_status(quiet: bool = False) -> WGStatusReport:
    """Check if WireGuard is connected and get current server info
    
    Args:
        quiet: If True, suppress printing status messages
        
    Returns:
        WGStatusReport object containing connection status and details
    """
    try:
        adapter = get_container_adapter()
        cmd_prefix = adapter.get_command_prefix()
        
        if not quiet:
            privileges_msg = "as root" if adapter.environment.is_container else "with sudo privileges"
            print(f"\nChecking WireGuard status (may require {privileges_msg})...")
        
        # Initialize an empty status report
        status_report = WGStatusReport(is_connected=False)
        
        # Check if any WireGuard interface is up
        result = subprocess.run(cmd_prefix + ['wg', 'show'], capture_output=True, text=True)
        
        if result.returncode != 0:
            return status_report
        
        # Check if wg0 interface is up
        is_connected = False
        wg_interfaces = result.stdout.strip().split('\n\n')
        for interface in wg_interfaces:
            if interface.startswith('interface: wg0'):
                is_connected = True
                break
        
        if not is_connected:
            return status_report
        
        # Update connection status
        status_report.is_connected = True
        
        # Get detailed information for the wg0 interface
        wg_output = subprocess.run(cmd_prefix + ['wg', 'show', 'wg0'], capture_output=True, text=True).stdout
        
        # Parse the output
        interface_details = _parse_wg_interface_output(wg_output)
        status_report.interface_details = interface_details

        if not interface_details:
            return status_report
        
        # Query the database to find the server
        from models.database_management import DatabaseClient
        with DatabaseClient() as db:
            server_record, find_method = _find_server_in_db(interface_details, db)
            
            if server_record:
                # Create app server info if we found a server
                app_server_info = ConnectedServerAppInfo(
                    country=server_record.country,
                    city=server_record.city,
                    load=server_record.load,
                    hostname=server_record.hostname,
                    endpoint=interface_details.endpoint,
                    latest_handshake=interface_details.latest_handshake,
                    transfer=interface_details.transfer,
                    found_by=find_method
                )
                status_report.app_server_info = app_server_info
            else:
                # If no match found in database, store the raw details
                status_report.raw_unmatched_details = interface_details
        
        return status_report
        
    except subprocess.CalledProcessError as e:
        if e.returncode == 1 and not quiet:
            privileges_msg = "you are running as root" if get_container_adapter().environment.is_container else "you have sudo privileges"
            print(f"\n{RED}Error: Failed to check WireGuard status. Please ensure {privileges_msg}.{RESET}")
        logger.error(f"Error checking WireGuard status: {e}")
        return WGStatusReport(is_connected=False)
    except WireGuardError as e:
        logger.error(f"WireGuard operation error: {e}")
        return WGStatusReport(is_connected=False)
    except DatabaseError as e:
        logger.error(f"Database error during status check: {e}")
        return WGStatusReport(is_connected=False)
    except Exception as e:
        # Only catch truly unexpected errors here
        logger.error(f"Unexpected error checking WireGuard status: {e}")
        return WGStatusReport(is_connected=False)

def manage_connection(config_manager: ConfigManager) -> None:
    """Handle connection management (connect/disconnect)"""
    print(CLEAR_SCREEN)
    display_header()
    
    # Check if wireguard config exists
    config_path = Path(config_manager.get('output', 'config_wg_file', '/etc/wireguard/wg0.conf'))
    if not check_file_exists_with_sudo(str(config_path)):
        print(f"\n{RED}Error: WireGuard configuration file not found at {config_path}.{RESET}")
        print("Please select a server and generate a configuration file first.")
        safe_input("\nPress Enter to return to menu...")
        return
    
    # Check current status
    status_report = check_wireguard_status()
    
    # Display options and get command
    command = display_connection_menu_options(status_report)
    
    if not command:
        print("\nOperation cancelled.")
        safe_input("\nPress Enter to return to menu...")
        return
    
    # Execute the selected command
    try:
        if command == "up":
            success = _perform_connect_action(config_path)
        elif command == "down":
            success = _perform_disconnect_action()
        elif command == "restart":
            success = _perform_restart_action(config_path)
            
        if success:
            print(f"\n{GREEN}✓ Command executed successfully!{RESET}")
        else:
            print(f"\n{RED}✗ Failed to execute command.{RESET}")
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Command execution failed: {e}")
        print(f"\n{RED}✗ Command failed with exit code {e.returncode}{RESET}")
    except WireGuardError as e:
        logger.error(f"WireGuard operation error: {e}")
        print(f"\n{RED}✗ WireGuard error: {e.message}{RESET}")
    except PermissionError as e:
        logger.error(f"Permission denied executing command: {e}")
        privileges_msg = "you are running as root" if get_container_adapter().environment.is_container else "you have sudo privileges"
        print(f"\n{RED}✗ Permission denied. Please ensure {privileges_msg}.{RESET}")
    except Exception as e:
        # Only catch truly unexpected errors here
        logger.error(f"Unexpected error executing command: {e}")
        print(f"\n{RED}✗ Unexpected error: {str(e)}{RESET}")
    
    safe_input("\nPress Enter to return to menu...")

def monitor_connection():
    """Curses-based live monitoring of WireGuard connection status"""
    def curses_main(stdscr):
        try:
            # Initialize monitor window
            monitor = MonitorWindow()
            monitor.stdscr = stdscr
            monitor.max_y, monitor.max_x = stdscr.getmaxyx()
            
            # Basic setup
            curses.curs_set(0)  # Hide cursor
            stdscr.nodelay(1)   # Make getch() non-blocking without timeout
            monitor.init_colors()
            monitor.create_windows()
            
            # Clear entire screen
            stdscr.clear()
            stdscr.refresh()
            
            # Track last update time
            last_update = 0
            update_interval = MONITOR_UPDATE_INTERVAL_MS / 1000  # Convert ms to seconds
            
            # Main loop
            while True:
                try:
                    # Check for terminal resize
                    new_y, new_x = stdscr.getmaxyx()
                    if new_y != monitor.max_y or new_x != monitor.max_x:
                        monitor.handle_resize()
                    
                    # Check for space key - immediate response
                    key = stdscr.getch()
                    if key == ord(' '):
                        break
                    
                    # Update display only if enough time has passed
                    current_time = time.time()
                    if current_time - last_update >= update_interval:
                        # Get current status
                        status_report = check_wireguard_status(quiet=True)
                        
                        # Update display
                        monitor.update_status(status_report)
                        monitor.update_footer()
                        monitor.refresh_all()
                        
                        last_update = current_time
                    
                    # Small sleep to prevent CPU hogging
                    curses.napms(1)  # 1ms sleep between key checks
                    
                except curses.error as e:
                    if "Terminal too small" in str(e):
                        stdscr.clear()
                        stdscr.addstr(0, 0, "Terminal too small. Please resize.")
                        stdscr.refresh()
                        continue
                    raise
                    
        finally:
            # Ensure proper cleanup
            monitor.cleanup()
            stdscr.clear()
            stdscr.refresh()
            curses.endwin()
    
    try:
        # Run the curses application
        curses.wrapper(curses_main)
    except curses.error as e:
        logger.error(f"Curses error in monitor: {e}")
        # Ensure terminal is properly reset
        try:
            curses.endwin()
        except Exception:
            pass
    except UIError as e:
        logger.error(f"UI error in monitor: {e}")
        try:
            curses.endwin()
        except Exception:
            pass
    except Exception as e:
        # Only catch truly unexpected errors here
        logger.error(f"Unexpected error in monitor: {e}")
        # Ensure terminal is properly reset
        try:
            curses.endwin()
        except Exception:
            pass

def update_server_list(config_manager: ConfigManager):
    """Handle server list update"""
    print("\nUpdate Server List")
    print("=" * UI_SEPARATOR_WIDTH_SMALL)
    limit = safe_input("How many servers to fetch? (default: 0 for no limit): ") or "0"
    
    try:
        limit = int(limit)
        new_count, prev_count = init_database(limit, config_manager)
        
        print("\n" + "=" * 50)
        if limit == 0:
            print(f"{GREEN}✓ Successfully updated server list with all available servers!{RESET}")
        else:
            print(f"{GREEN}✓ Successfully updated server list with {limit} servers!{RESET}")
            
        # Show database statistics
        if prev_count > 0:
            diff = new_count - prev_count
            if diff > 0:
                print(f"{GREEN}✓ Added {diff} new servers{RESET}")
            elif diff < 0:
                print(f"{GREEN}✓ Removed {abs(diff)} servers{RESET}")
            else:
                print(f"{GREEN}✓ No changes in server count{RESET}")
        print(f"{GREEN}✓ Total servers in database: {new_count}{RESET}")
        
        # Show last update time
        last_update = get_last_update_time(config_manager, format_as_time_ago=True)
        print(f"{GREEN}✓ Last update: {last_update}{RESET}")
        print("=" * 50 + "\n")
        
    except ValueError:
        print("Please enter a valid number. Pay attention, buddy :-)")
    except Exception as e:
        print(f"Error updating server list in {config_manager.get('database', 'path', 'servers.db')}: {e}")

def show_top_servers(config_manager: ConfigManager) -> List[Dict]:
    """Show top servers globally with lowest load"""
    display_header()
    print(f"\nTop {TOP_SERVERS_LIMIT} Global Servers")
    print("=" * UI_SEPARATOR_WIDTH_SMALL)
    
    try:
        # Get database path from config manager
        db_path = config_manager.get('database', 'path', 'servers.db')
        servers = get_best_servers(
            country=None,  # No country filter
            max_load=DEFAULT_MAX_LOAD,  # Consider all servers
            limit=TOP_SERVERS_LIMIT,      # Top 10 only
            db_path=db_path  # Pass the database path
        )
        
        if not servers:
            print("\nNo VPN servers found in local database. Please go back to the main menu and update the local database first.")
            return []
            
        display_server_options(servers)
        return servers
            
    except Exception as e:
        logger.error(f"Error finding servers: {e}")
        print("\nError occurred while searching for VPN servers. Please try again.")
        return []

def select_vpn_endpoint(config_manager: ConfigManager):
    """Select VPN endpoint by criteria"""
    print(CLEAR_SCREEN)
    display_header()
    print("\nSelect VPN Endpoint")
    print("=" * UI_SEPARATOR_WIDTH_SMALL)
    print("1. Search by country")
    print(f"2. Show top {TOP_SERVERS_LIMIT} servers globally")
    print("3. Return to main menu")
    
    choice = safe_input("\nSelect an option (1-3): ").strip()
    
    if choice == '1':
        servers = select_by_country(config_manager)
    elif choice == '2':
        servers = show_top_servers(config_manager)
    else:
        return
    
    if servers:
        # List is not empty, prompt for server selection
        generate_config_from_list(servers, config_manager)

def select_by_country(config_manager: ConfigManager) -> List[ServerDBRecord]:
    """Select servers by country"""
    display_header()
    print("\nSelect Server by Country")
    print("=" * UI_SEPARATOR_WIDTH_SMALL)
    
    try:
        # Get available countries first
        with DatabaseClient() as db:
            db.cursor.execute('SELECT DISTINCT country FROM servers ORDER BY country')
            available_countries = [row[0] for row in db.cursor.fetchall()]
            
        if not available_countries:
            print("\nNo servers found in database. Please run 'Update server list' first.")
            return []
        
        # Display UI and get country selection
        country = display_country_selection_ui(available_countries)
        if not country:
            return []
            
        # Get servers for selected country
        db_path = config_manager.get('database', 'path', 'servers.db')
        servers = get_best_servers(
            country=country,
            max_load=DEFAULT_MAX_LOAD,  # Consider all servers
            limit=TOP_SERVERS_LIMIT,      # Show top 10 from country
            db_path=db_path  # Pass the database path
        )
        
        if not servers:
            print("\nNo servers found in the selected country.")
            return []
            
        # Update header with selected country
        display_header()
        print(f"\nTop {TOP_SERVERS_LIMIT} Servers in {country}")
        print("=" * UI_SEPARATOR_WIDTH_SMALL)
        display_server_options(servers)
        return servers
            
    except Exception as e:
        logger.error(f"Error finding servers: {e}")
        print("\nError occurred while searching for servers. Please try again.")
        return []

def generate_config_from_list(servers: List[ServerDBRecord], config_manager: ConfigManager) -> bool:
    """Generate WireGuard config from a list of servers
    
    Args:
        servers: List of server records to choose from
        config_manager: ConfigManager instance
        
    Returns:
        True if config was successfully generated, False otherwise
    """
    if not servers:
        return False
        
    # Prompt for server selection
    selected_server = prompt_server_selection(servers)
    if not selected_server:
        return False
    
    # Generate config
    try:
        # Get the output path from config
        config_path = Path(config_manager.get('output', 'config_wg_file'))
        
        # Disconnect from VPN if already connected
        if not _handle_pre_apply_disconnect():
            return False
            
        # Generate the config content
        config_content = generate_wireguard_config(selected_server, config_manager)
        
        # Write config to file with sudo
        if not _write_config_sudo(config_content, config_path):
            return False
            
        print(f"\n{GREEN}✓ WireGuard configuration successfully generated at {config_path}{RESET}")
        
        # Ask user if they want to connect now
        if safe_input("\nWould you like to connect now? (Y/n): ").lower().strip() != 'n':
            return _handle_post_apply_connect(config_path)
        
        return True
            
    except Exception as e:
        logger.error(f"Error generating WireGuard config: {e}")
        print(f"\n{RED}Error: {str(e)}{RESET}")
        return False

def _run_with_progress(command: List[str], description: str, duration_estimate: float = 2.0) -> subprocess.CompletedProcess:
    """Run a command with a simple progress indicator
    
    Args:
        command: Command to run
        description: Description to show in progress bar
        duration_estimate: Estimated duration in seconds
        
    Returns:
        CompletedProcess result
    """
    with tqdm(total=100, desc=description, bar_format='{desc}: {bar} {percentage:3.0f}%', ncols=80) as pbar:
        # Start the process
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Show progress while waiting
        start_time = time.time()
        while process.poll() is None:
            elapsed = time.time() - start_time
            progress = min(95, int((elapsed / duration_estimate) * 100))
            pbar.n = progress
            pbar.refresh()
            time.sleep(0.1)
        
        # Complete the progress bar
        pbar.n = 100
        pbar.refresh()
        
        # Get the result
        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

def _perform_disconnect_action() -> bool:
    """Perform WireGuard disconnect action
    
    Returns:
        True if successful, False otherwise
    """
    print(f"\nDisconnecting from VPN...")
    adapter = get_container_adapter()
    cmd_prefix = adapter.get_command_prefix()
    result = _run_with_progress(cmd_prefix + ['wg-quick', 'down', 'wg0'], "Disconnecting", 1.5)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
        
    success = result.returncode == 0
    if success:
        print(f"\n{GREEN}✓ Disconnected from VPN successfully!{RESET}")
    else:
        print(f"\n{RED}✗ Failed to disconnect from VPN. Error code: {result.returncode}{RESET}")
    
    return success

def _perform_connect_action(config_path: Path) -> bool:
    """Perform WireGuard connect action
    
    Args:
        config_path: Path to WireGuard config file
        
    Returns:
        True if successful, False otherwise
    """
    print(f"\nConnecting to VPN...")
    adapter = get_container_adapter()
    cmd_prefix = adapter.get_command_prefix()
    result = _run_with_progress(cmd_prefix + ['wg-quick', 'up', str(config_path)], "Connecting", 2.5)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
        
    success = result.returncode == 0
    if success:
        print(f"\n{GREEN}✓ Connected to VPN successfully!{RESET}")
    else:
        print(f"\n{RED}✗ Failed to connect to VPN. Error code: {result.returncode}{RESET}")
    
    return success

def _perform_restart_action(config_path: Path) -> bool:
    """Perform WireGuard restart action
    
    Args:
        config_path: Path to WireGuard config file
        
    Returns:
        True if successful, False otherwise
    """
    adapter = get_container_adapter()
    cmd_prefix = adapter.get_command_prefix()
    
    # First disconnect
    print(f"\nRestarting VPN connection...")
    result_down = _run_with_progress(cmd_prefix + ['wg-quick', 'down', 'wg0'], "Disconnecting", 1.5)
    if result_down.stdout:
        print(result_down.stdout)
    if result_down.stderr:
        print(result_down.stderr)
        
    # Add a small delay to ensure interface is fully down
    time.sleep(1)
        
    # Then connect again
    result_up = _run_with_progress(cmd_prefix + ['wg-quick', 'up', str(config_path)], "Connecting", 2.5)
    if result_up.stdout:
        print(result_up.stdout)
    if result_up.stderr:
        print(result_up.stderr)
        
    success = result_down.returncode == 0 and result_up.returncode == 0
    if success:
        print(f"\n{GREEN}✓ Connection restarted successfully!{RESET}")
    else:
        print(f"\n{RED}✗ Failed to restart connection{RESET}")
    
    return success

def _handle_pre_apply_disconnect() -> bool:
    """Handle disconnection before applying a new configuration
    
    Returns:
        True if disconnect succeeded or user confirmed to continue anyway, False otherwise
    """
    status_report = check_wireguard_status(quiet=True)
    if status_report.is_connected:
        print(f"\n{YELLOW}Disconnecting from current VPN before applying new config...{RESET}")
        try:
            adapter = get_container_adapter()
            cmd_prefix = adapter.get_command_prefix()
            result = subprocess.run(cmd_prefix + ['wg-quick', 'down', 'wg0'], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"\n{RED}Error disconnecting from VPN: {result.stderr}{RESET}")
                return safe_input("\nContinue anyway? (y/n): ").lower().strip() == 'y'
            else:
                print(f"\n{GREEN}Successfully disconnected from VPN.{RESET}")
                # Small delay to ensure clean disconnect
                time.sleep(1)
                return True
        except Exception as e:
            print(f"\n{RED}Error: {str(e)}{RESET}")
            return safe_input("\nContinue anyway? (y/n): ").lower().strip() == 'y'
    return True  # Not connected, so no need to disconnect

def _write_config_sudo(config_content: str, config_path: Path) -> bool:
    """Write WireGuard config to file with proper privileges
    
    Args:
        config_content: WireGuard config content to write
        config_path: Path to write the config to
        
    Returns:
        True if successful, False otherwise
    """
    try:
        adapter = get_container_adapter()
        cmd_prefix = adapter.get_command_prefix()
        
        # Write config ensuring proper permissions
        wg_filename = Path(config_path).name
        tmp_path = Path('/tmp') / f"{wg_filename}.tmp"
        with open(tmp_path, 'w') as f:
            f.write(config_content)
        
        # Copy to final location with appropriate privileges
        result = subprocess.run(cmd_prefix + ['cp', str(tmp_path), str(config_path)],
                            capture_output=True, text=True)
                        
        # Verify the config was properly written
        verify_result = subprocess.run(cmd_prefix + ['cat', str(config_path)],
                                    capture_output=True, text=True)
        
        # Cleanup temp file
        tmp_path.unlink()
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to write config: {result.stderr}")

        print("\n" + "=" * 50)
        print(f"{GREEN}✓ WireGuard config successfully saved to {config_path}{RESET}")
        return True
        
    except Exception as e:
        print(f"\n{RED}Error: {str(e)}{RESET}")
        return False

def _handle_post_apply_connect(config_path: Path) -> bool:
    """Handle connection after applying a new configuration
    
    Args:
        config_path: Path to the WireGuard config file
        
    Returns:
        True if successful, False otherwise
    """
    print(f"\n{YELLOW}Connecting to new VPN server...{RESET}")
    try:
        adapter = get_container_adapter()
        cmd_prefix = adapter.get_command_prefix()
        # Connect with new config
        result = subprocess.run(cmd_prefix + ['wg-quick', 'up', str(config_path)], 
                            capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"\n{GREEN}✓ Successfully connected to new VPN server!{RESET}")
            # Add delay to allow connection to stabilize
            time.sleep(2)
            # Clear screen and show new status
            print(CLEAR_SCREEN)
            display_header()
            return True
        else:
            print(f"\n{RED}Error connecting to VPN: {result.stderr}{RESET}")
            return False
    except Exception as e:
        print(f"\n{RED}Error: An unexpected error occurred{RESET}")
        print(f"Details: {e}")
        return False

def generate_wireguard_config(server: ServerDBRecord, config_manager: ConfigManager) -> str:
    """Generate WireGuard configuration"""
    config = WireGuardConfig.from_server(server, config_manager)
    return config.generate()
