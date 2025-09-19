import curses
import time
import logging
from typing import Optional

from models.data_models import ConnectedServerAppInfo, WGTransferInfo, WGStatusReport
from models.core.exceptions import UIError
from models.core.constants import TERMINAL_MIN_WIDTH, TERMINAL_MIN_HEIGHT

logger = logging.getLogger(__name__)

class MonitorWindow:
    """Curses-based monitoring window manager"""
    def __init__(self):
        self.stdscr = None
        self.max_y = 0
        self.max_x = 0
        self.status_win = None
        self.transfer_win = None
        self.footer_win = None
        
    def init_colors(self):
        """Initialize color pairs"""
        curses.start_color()
        curses.use_default_colors()  # Use terminal's default colors
        curses.init_pair(1, curses.COLOR_GREEN, -1)    # Connected
        curses.init_pair(2, curses.COLOR_RED, -1)      # Disconnected
        curses.init_pair(3, curses.COLOR_CYAN, -1)     # Headers
        
    def create_windows(self):
        """Create sub-windows for different panels"""
        # Cleanup existing windows first
        self.cleanup()
        
        # Calculate dimensions
        status_height = 8
        transfer_height = 5
        footer_height = 3
        
        # Create windows with borders
        self.status_win = curses.newwin(status_height, self.max_x-2, 1, 1)
        self.transfer_win = curses.newwin(transfer_height, self.max_x-2, 
                                        status_height+1, 1)
        self.footer_win = curses.newwin(footer_height, self.max_x-2, 
                                      self.max_y-footer_height-1, 1)
        
        # Add borders to all windows
        for win in [self.status_win, self.transfer_win, self.footer_win]:
            win.box()
            
    def update_status(self, status_report: WGStatusReport) -> None:
        """Update status window with connection information
        
        Args:
            status_report: WireGuard status report Pydantic model
        """
        if not self.status_win:
            return
            
        self.status_win.clear()
        self.status_win.box()
        
        y = 1  # Start position
        if status_report.is_connected:
            self.status_win.addstr(y, 2, "● Connected", 
                                curses.color_pair(1) | curses.A_BOLD)
            
            # Display server information if available
            if status_report.app_server_info:
                self._display_server_info(status_report.app_server_info)
                
                # Update transfer information if available
                if status_report.interface_details and status_report.interface_details.transfer:
                    self.update_transfer(status_report.interface_details.transfer)
            
            # If server info not available but we have interface details
            elif status_report.raw_unmatched_details:
                y += 1
                self.status_win.addstr(y, 2, "Server: Unknown (not in database)")
                
                if status_report.raw_unmatched_details.endpoint:
                    y += 1
                    self.status_win.addstr(y, 2, f"Endpoint: {status_report.raw_unmatched_details.endpoint}")
                
                if status_report.raw_unmatched_details.latest_handshake:
                    y += 1
                    self.status_win.addstr(y, 2, f"Latest Handshake: {status_report.raw_unmatched_details.latest_handshake}")
                
                # Update transfer information
                self.update_transfer(status_report.raw_unmatched_details.transfer)
        else:
            self.status_win.addstr(y, 2, "○ Not Connected", 
                                curses.color_pair(2) | curses.A_BOLD)
    
    def _display_server_info(self, server_info: ConnectedServerAppInfo) -> None:
        """Display server information in the status window
        
        Args:
            server_info: Connected server information Pydantic model
        """
        if not self.status_win:
            return
            
        y = 2  # Start from the second line (after connection status)
        self.status_win.addstr(y, 2, f"Server: {server_info.country}, "
                           f"{server_info.city} (Load: {server_info.load}%)")
        y += 1
        self.status_win.addstr(y, 2, f"Hostname: {server_info.hostname}")
        
        if server_info.endpoint:
            y += 1
            self.status_win.addstr(y, 2, f"Endpoint: {server_info.endpoint}")
            
        if server_info.latest_handshake:
            y += 1
            self.status_win.addstr(y, 2, f"Latest Handshake: {server_info.latest_handshake}")
                                
    def update_transfer(self, transfer_info: WGTransferInfo) -> None:
        """Update transfer statistics window
        
        Args:
            transfer_info: WireGuard transfer information Pydantic model
        """
        if not self.transfer_win:
            return
            
        self.transfer_win.clear()
        self.transfer_win.box()
        
        y = 1  # Start position
        self.transfer_win.addstr(y, 2, "Transfer Statistics", 
                              curses.color_pair(3) | curses.A_BOLD)
        y += 1
        self.transfer_win.addstr(y, 2, f"↓ Received: {transfer_info.received}")
        y += 1
        self.transfer_win.addstr(y, 2, f"↑ Sent:     {transfer_info.sent}")
        
    def update_footer(self) -> None:
        """Update footer with instructions"""
        if not self.footer_win:
            return
            
        self.footer_win.clear()
        self.footer_win.box()
        
        # Center the "Press SPACE to return" message
        message = "Press SPACE to return"
        x = (self.max_x - len(message)) // 2
        self.footer_win.addstr(1, x, message, curses.A_BOLD)
                            
    def handle_resize(self) -> None:
        """Handle terminal resize events"""
        self.max_y, self.max_x = self.stdscr.getmaxyx()
        if self.max_y < TERMINAL_MIN_HEIGHT or self.max_x < TERMINAL_MIN_WIDTH:
            raise curses.error("Terminal too small")
        self.create_windows()
        
    def refresh_all(self) -> None:
        """Refresh all windows"""
        if not all([self.stdscr, self.status_win, self.transfer_win, self.footer_win]):
            return
            
        self.stdscr.noutrefresh()
        self.status_win.noutrefresh()
        self.transfer_win.noutrefresh()
        self.footer_win.noutrefresh()
        curses.doupdate()
        
    def cleanup(self) -> None:
        """Clean up curses windows"""
        # Delete windows in reverse order
        for win_attr in ['footer_win', 'transfer_win', 'status_win']:
            win = getattr(self, win_attr)
            if win:
                try:
                    win.clear()
                    win.refresh()
                    del win
                except (AttributeError, curses.error) as e:
                    logger.warning(f"Error cleaning up window {win_attr}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error cleaning up window {win_attr}: {e}")
            setattr(self, win_attr, None)
