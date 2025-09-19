"""
UI helper functions and constants for rendering the application interface.

This module centralizes all UI-related code to improve organization and reduce
duplication across the application.
"""
import sys
from typing import List, Dict, Optional, Union, Any

from models.data_models import WGStatusReport, ServerDBRecord, SystemdServiceStatus
from models.core.constants import (
    UI_SEPARATOR_WIDTH_MEDIUM, UI_SEPARATOR_WIDTH_LARGE, COLUMN_WIDTH_DEFAULT,
    COLUMN_COUNT_COUNTRIES, MAX_OPTION_LENGTH_PADDING
)

# Color constants
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
CLEAR_SCREEN = "\033[2J\033[H"


def safe_input(prompt: str) -> str:
    """Wrapper for input() that handles keyboard interrupt
    
    Args:
        prompt: Input prompt to display
        
    Returns:
        User input as string
    """
    try:
        return input(prompt)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        print("Exiting...")
        sys.exit(0)


def display_header(current_server: Optional[ServerDBRecord] = None) -> None:
    """Display program header with current connection status
    
    Args:
        current_server: Currently selected server (if any)
    """
    from models.connection_management import check_wireguard_status
    from models.service_management import check_systemd_available, check_systemd_status
    
    print("\nNordVPN WireGuard Manager")
    print("=" * UI_SEPARATOR_WIDTH_MEDIUM)
    
    # Check current connection status
    status_report = check_wireguard_status(quiet=True)
    
    if status_report.is_connected:
        if status_report.app_server_info:
            server_info = status_report.app_server_info
            print(f"{GREEN}● Connected{RESET}")
            print(f"Server: {server_info.country}, {server_info.city} (Load: {server_info.load}%)")
            print(f"Hostname: {server_info.hostname}")
            if server_info.endpoint:
                print(f"Endpoint: {server_info.endpoint}")
                if server_info.found_by is None:
                    print(f"{RED}Note: Endpoint not found in database{RESET}")
            if server_info.latest_handshake:
                print(f"Latest Handshake: {server_info.latest_handshake}")
            print(f"Transfer: ↓ {server_info.transfer.received} received, ↑ {server_info.transfer.sent} sent")
        else:
            print(f"{GREEN}● Connected{RESET} | Server details not available")
    else:
        print(f"{RED}○ Not Connected{RESET}")
    
    # Check for systemd autostart status if available
    if check_systemd_available():
        status = check_systemd_status()
        if status.exists:
            service_type = "User" if status.user_mode else "System"
            if status.enabled:
                print(f"{GREEN}● Autostart Enabled{RESET} ({service_type}-level)")
            else:
                print(f"{YELLOW}○ Autostart Configured but Not Enabled{RESET} ({service_type}-level)")
    
    if current_server:
        print("-" * UI_SEPARATOR_WIDTH_MEDIUM)
        print(f"Selected Server | {current_server.country}, {current_server.city} (Load: {current_server.load}%)")
    
    print("=" * UI_SEPARATOR_WIDTH_MEDIUM)


def display_server_options(servers: List[ServerDBRecord]) -> None:
    """Display available server options
    
    Args:
        servers: List of server records to display
    """
    print("\nAvailable servers:")
    print("-" * UI_SEPARATOR_WIDTH_LARGE)
    print(f"{'ID':<4} {'Hostname':<30} {'Country':<20} {'City':<15} {'Load':<5}")
    print("-" * UI_SEPARATOR_WIDTH_LARGE)
    
    for idx, server in enumerate(servers, 1):
        print(f"{idx:<4} {server.hostname:<30} {server.country:<20} "
              f"{server.city:<15} {server.load}%")


def display_service_status(status: SystemdServiceStatus) -> None:
    """Display the current service status
    
    Args:
        status: The SystemdServiceStatus object
    """
    service_type = "User" if status.user_mode else "System"
    print(f"\nService Status: {service_type}-level service")
    print(f"Path: {status.path}")
    print(f"Enabled at boot: {GREEN}Yes{RESET}" if status.enabled else f"Enabled at boot: {RED}No{RESET}")
    print(f"Currently active: {GREEN}Yes{RESET}" if status.active else f"Currently active: {RED}No{RESET}")


def display_country_selection_ui(available_countries: List[str]) -> Optional[str]:
    """Display a UI for selecting a country from a list
    
    Args:
        available_countries: List of available country names
        
    Returns:
        Selected country name or None if selection failed
    """
    # Simple filter option to improve UX with many countries
    print(f"\nFound {len(available_countries)} countries available.")
    filter_text = safe_input("Type first letters to filter countries (or press Enter to see all): ").strip()
    
    # Apply filter if provided
    countries_to_show = available_countries
    if filter_text:
        countries_to_show = [c for c in available_countries if c.upper().startswith(filter_text.upper())]
        if not countries_to_show:
            print(f"No countries found starting with '{filter_text}'. Showing all countries.")
            countries_to_show = available_countries
        else:
            print(f"Filtered to {len(countries_to_show)} countries starting with '{filter_text}':")
    
    # Show available countries with numbers in columns
    print("\nAvailable countries:")
    
    # Calculate number of rows needed for columns
    num_countries = len(countries_to_show)
    num_rows = (num_countries + COLUMN_COUNT_COUNTRIES - 1) // COLUMN_COUNT_COUNTRIES  # Round up division
    
    # Format each entry to have consistent width (number + country name)
    max_option_length = max(
        len(f"{idx}. {country}") 
        for idx, country in enumerate(countries_to_show, 1)
    )
    column_width = max(COLUMN_WIDTH_DEFAULT, max_option_length + MAX_OPTION_LENGTH_PADDING)  # Minimum default chars, or longer if needed
    
    # Print countries in columns
    for row in range(num_rows):
        line = ""
        for col in range(COLUMN_COUNT_COUNTRIES):
            idx = row + (col * num_rows)
            if idx < num_countries:
                country = countries_to_show[idx]
                option = f"{idx + 1}. {country}"
                line += option.ljust(column_width)
        print(line.rstrip())
        
    # Get country selection by number
    while True:
        try:
            choice = int(safe_input("\nEnter country number: ").strip())
            if 1 <= choice <= len(countries_to_show):
                return countries_to_show[choice - 1]
            print(f"Invalid choice. Please enter a number between 1 and {len(countries_to_show)}.")
        except ValueError:
            print("Please enter a valid number.")
            
    return None


def prompt_server_selection(servers: List[ServerDBRecord]) -> Optional[ServerDBRecord]:
    """Prompt user to select a server from a list
    
    Args:
        servers: List of servers to choose from
        
    Returns:
        Selected server or None if selection failed
    """
    try:
        choice = int(safe_input("\nEnter server number to generate config: "))
        if not (1 <= choice <= len(servers)):
            print("Invalid selection. Please try again.")
            return None
                
        selected_server = servers[choice - 1]
        print(f"\nSelected server: {selected_server.hostname} ({selected_server.country}, {selected_server.city})")
        return selected_server
        
    except ValueError:
        print("Please enter a valid number.")
        return None


def display_connection_menu_options(status_report: WGStatusReport) -> Optional[str]:
    """Display connection menu options based on current connection status
    
    Args:
        status_report: Current WireGuard status report
        
    Returns:
        Command to execute ('up', 'down', 'restart') or None to cancel
    """
    print("\nWireGuard Connection Manager")
    print("=" * UI_SEPARATOR_WIDTH_MEDIUM)
    
    if status_report.is_connected:
        print(f"{GREEN}● Currently Connected{RESET}")
        if status_report.app_server_info:
            server_info = status_report.app_server_info
            print(f"Connected to: {server_info.country}, {server_info.city} (Load: {server_info.load}%)")
        elif status_report.interface_details and status_report.interface_details.endpoint:
            endpoint = status_report.interface_details.endpoint
            print(f"Connected to: {endpoint}")
            
        print("\nOptions:")
        print("1. Disconnect")
        print("2. Restart connection")
        print("3. Cancel")
        
        choice = safe_input("\nSelect an option (1-3): ").strip()
        
        if choice == '1':
            return "down"
        elif choice == '2':
            return "restart"
        else:
            return None
    else:
        print(f"{RED}○ Not Connected{RESET}")
        print("\nOptions:")
        print("1. Connect")
        print("2. Cancel")
        
        if safe_input("\nSelect an option (1-2): ").strip() == '1':
            return "up"
        return None 