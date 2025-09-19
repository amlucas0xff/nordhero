App Flow Document - NordVPN WireGuard Manager
Version: v1.0
Date of Last Update: May 14, 2025
Authors: Project Development Team
1. Purpose and Scope
This document maps out the core workflows and interaction sequences in the NordVPN WireGuard Manager application from both user and system perspectives.
Scope: The document covers:

Initial application setup and configuration
Server database management
VPN server selection and configuration
Connection management (connect/disconnect)
Real-time connection monitoring
Systemd service management for autostart

2. Target Audience
This document is intended for:

Developers working on the application
QA engineers testing the application
System administrators deploying the solution
Technical documentation writers

3. High-Level Flow Diagram
```
[User] → [Main Menu] → ┬→ [Update Server List] → [NordVPN API] → [SQLite DB]
                      ├→ [Select VPN Endpoint] → [Generate Config] → [WireGuard]
                      ├→ [Manage connection] → [WireGuard Service]
                      ├→ [Monitor connection] → [Real-time Display]
                      └→ [Configure systemd service] → [systemd Service]
```
4. User Personas & Use Cases
Primary User: Linux system administrator or power user
Key Use Cases:

Configure and connect to NordVPN via WireGuard protocol
Monitor VPN connection status in real-time
Set up automatic VPN connection on system boot
Manage multiple VPN server configurations

5. Detailed Screen-to-Screen Flow
5.1 Initial Setup Flow
```
[Application Start]
    ↓
[Check for config.toml]
    ↓ (if not exists)
[Create Configuration]
    ↓
[Prompt for WireGuard Private Key]
    ↓
[Prompt for Client IP]
    ↓
[Save Configuration]
    ↓
[Main Menu]
```
5.2 Server Database Update Flow
```
[Main Menu]
    ↓
[Select "Update Server List"]
    ↓
[Prompt for Server Limit]
    ↓
[Call NordVPN API]
    ↓
[Display Progress Bar]
    ↓
[Import to SQLite]
    ↓
[Show Update Statistics]
    ↓
[Return to Main Menu]
```
5.3 VPN Server Selection Flow
```
[Main Menu]
    ↓
[Select "Select VPN Endpoint"]
    ↓
[Choose Selection Method]
    ├─→ [Search by Country]
    │     ↓
    │   [Display Countries]
    │     ↓
    │   [Select Country]
    │     ↓
    │   [Show Top 10 Servers]
    │
    └─→ [Show Global Top 10]
          ↓
[Display Server List]
    ↓
[Select Server Number]
    ↓
[Generate WireGuard Config]
    ↓
[Save to /etc/wireguard/wg0.conf]
    ↓
[Prompt to Connect Now]
5.4 Connection Management Flow
[Main Menu]
    ↓
[Select "Manage Connection"]
    ↓
[Check Current Status]
    ↓
[Display Connection Options]
    ├─→ [Connect] → Execute: sudo wg-quick up wg0
    ├─→ [Disconnect] → Execute: sudo wg-quick down wg0
    └─→ [Restart] → Execute: down then up
    ↓
[Show Command Output]
    ↓
[Return to Main Menu]
```
5.5 Connection Monitoring Flow
```
[Main Menu]
    ↓
[Select "Monitor Connection"]
    ↓
[Initialize Curses Display]
    ↓
[Real-time Update Loop]
    ├─→ [Status Window] - Connection status
    ├─→ [Transfer Window] - Data transfer stats
    └─→ [Footer Window] - Exit instructions
    ↓ (Press SPACE)
[Exit Monitor]
    ↓
[Return to Main Menu]
```
5.6 Autostart Configuration Flow
```
[Main Menu]
    ↓
[Select "Configure Autostart"]
    ↓
[Check Systemd Availability]
    ↓
[Check Existing Service]
    ├─→ [Service Exists]
    │     ↓
    │   [Management Options]
    │     ├─→ [Enable/Disable]
    │     ├─→ [Start/Stop]
    │     └─→ [Recreate Service]
    │
    └─→ [No Service]
          ↓
        [Create Service Options]
          ├─→ [System-level]
          └─→ [User-level]
    ↓
[Execute Selected Action]
    ↓
[Return to Main Menu]
```
6. API and Backend Interaction Points
6.1 NordVPN API Integration

Endpoint: https://api.nordvpn.com/v1/servers/recommendations
Purpose: Fetch WireGuard server information
Parameters:

filters[servers_technologies][identifier]: "wireguard_udp"
limit: Number of servers to fetch


Response Format: JSON array of server objects

6.2 WireGuard System Commands

Connect: sudo wg-quick up wg0
Disconnect: sudo wg-quick down wg0
Status Check: sudo wg show wg0

6.3 Systemd Integration

Service Creation: Write unit file to /etc/systemd/system/
Service Control: systemctl enable/disable/start/stop nordvpn-wireguard

7. Data Flow Mapping
```
[NordVPN API] → [JSON Response] → [Parse & Validate] → [SQLite Database]
                                                          ↓
[User Selection] ← [Display Server List] ← [Query Database]
      ↓
[Generate Config] → [Write to File] → [WireGuard Service]
```
7.1 Configuration Data Structure
```
toml[wireguard]
private_key_file = "config/wireguard.key"
client_ip = "10.5.0.2/32"
dns = "192.168.68.14"
persistent_keepalive = 25

[database]
path = "servers.db"
max_load = 100
default_limit = 0

[output]
config_dir = "/etc/wireguard"
config_wg_file = "/etc/wireguard/wg0.conf"
```
8. State Management Strategy
The application uses a stateless design with configuration and connection state persisted through:

Configuration: TOML file (config/config.toml)
Server Data: SQLite database (servers.db)
Connection State: WireGuard service status
Private Key: Separate file with restricted permissions

9. UX/UI Considerations

CLI Interface: Text-based menu system with numbered options
Color Coding:

GREEN: Connected/Success states
RED: Disconnected/Error states
YELLOW: Warning/Intermediate states


Progress Indicators: Visual progress bars for long operations
Real-time Updates: Curses-based monitoring with 900ms refresh rate

10. Accessibility and Internationalization Notes

Keyboard Navigation: All functions accessible via keyboard
Clear Text Output: Compatible with terminal screen readers
Error Messages: Descriptive error messages for troubleshooting

11. Edge Cases and Error Handling
11.1 Connection Errors

Missing Config File: Prompt user to generate configuration
Permission Denied: Request sudo privileges
Service Failure: Display detailed error logs

11.2 API Failures

Network Timeout: Configurable timeout (default: 10s)
Invalid Response: Data validation with Pydantic models
Empty Results: Graceful handling with user notification

11.3 File System Errors

Read/Write Permissions: Check before operations
Missing Directories: Create with appropriate permissions
File Locks: Handle concurrent access gracefully

12. Integration Points
12.1 External Services

NordVPN API: Server information retrieval
WireGuard: VPN protocol implementation
Systemd: Service management for autostart

12.2 System Dependencies

sudo: Required for privileged operations
wg-quick: WireGuard configuration management
systemctl: Service control

13. Related Documentation

WireGuard Configuration Reference
NordVPN API Documentation
Systemd Service Management Guide
SQLite Database Schema

14. Change History
VersionDateChangesAuthorv1.02025-05-14Initial documentationDevelopment Team
Agile Implementation Notes

Update Frequency: End of each sprint
Storage Location: Project repository /docs
Review Process: Team review during sprint planning
Visual Tools: Mermaid diagrams for flow visualization
