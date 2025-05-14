# Nordhero

A command-line interface (CLI) tool for managing NordVPN connections using the WireGuard protocol on Linux systems. This tool provides an easy way to connect to NordVPN's WireGuard servers with features like server selection, connection monitoring, and automatic startup configuration.
Features

- **Server Database Management** - Automatically fetch and update NordVPN WireGuard server list
- **Smart Server Selection** - Choose servers by country or view top global performers
- **Connection Management** - Easy connect/disconnect/restart operations
- **Real-time Monitoring** - Live connection status and transfer statistics
- **Autostart Configuration** - Set up automatic VPN connection on system boot via systemd
- **Secure Configuration** - Private key stored separately with restricted permissions
- **User-friendly CLI** - Color-coded interface with clear navigation

## Sample
```
NordVPN WireGuard Manager
==================================================
● Connected
Server: United States, New York (Load: 45%)
Hostname: us123.nordvpn.com
Endpoint: 192.168.1.1
Latest Handshake: 2 seconds ago
Transfer: ↓ 1.2 GB received, ↑ 340 MB sent
● Autostart Enabled (System-level)
==================================================

Main Menu:
1. Update server list
2. Select VPN endpoint
3. Manage connection (connect/disconnect)
4. Monitor connection
5. Configure autostart
6. Exit

Select an option (1-6):
```

## Requirements

### System Requirements
- Linux operating system
- Python 3.8 or higher
- WireGuard installed (`wg` and `wg-quick` commands)
- sudo privileges for VPN operations
- systemd (for autostart feature)

### Python Dependencies
```txt
pydantic>=2.0
requests
toml
tqdm
sqlite3 (built-in)
curses (built-in)
```

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/amlucas0xff/nordhero.git
cd nordhero
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Make the main script executable:**
```bash
chmod +x main.py
```

## Initial Setup

Before using the application, you'll need:

1. **NordVPN Account** - Active subscription with WireGuard access
2. **WireGuard Private Key** - Generate from your NordVPN account dashboard
3. **Client IP Address** - Assigned by NordVPN (usually in 10.5.0.x/32 range)

### Configuration

On first run, the application will prompt you to enter:
- Your WireGuard private key
- Your assigned client IP address

The configuration is stored in `config/config.toml`:

```toml
[wireguard]
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

### Command Examples

The application manages WireGuard connections using standard commands:
- Connect: `sudo wg-quick up wg0`
- Disconnect: `sudo wg-quick down wg0`
- Status: `sudo wg show wg0`

## Project Structure

```
nordhero/
├── main.py                     # Main application entry point
├── config/                     # Configuration directory
│   ├── config.toml            # Application configuration
│   └── wireguard.key          # Private key (created on setup)
├── models/                     # Core application models
│   ├── config_management.py    # Configuration handling
│   ├── connection_management.py # VPN connection logic
│   ├── database_management.py  # SQLite operations
│   ├── data_models.py         # Pydantic data models
│   ├── monitor_management.py   # Real-time monitoring
│   ├── service_management.py   # Systemd service handling
│   ├── ui_helpers.py          # CLI interface utilities
│   ├── validator_management.py # Configuration validation
│   ├── wireguard_config.py    # WireGuard config generation
│   └── helpers.py             # Utility functions
├── api/                       # External API integrations
│   └── nordvpn_client/        # NordVPN API client
│       ├── wireguard.py       # API client implementation
│       ├── types.py           # API data types
│       └── exceptions.py      # Custom exceptions
├── docs/                      # Documentation
├── tests/                     # Test suite
└── requirements.txt           # Python dependencies
```

## Troubleshooting

### Common Issues

1. **Permission Denied:**
   - Ensure you have sudo privileges
   - Check file permissions on config files

2. **Connection Failed:**
   - Verify WireGuard is installed: `which wg-quick`
   - Check if another VPN is active
   - Ensure correct private key and client IP

3. **Service Not Starting:**
   - Check systemd logs: `sudo journalctl -u nordvpn-wireguard`
   - Verify config file exists at `/etc/wireguard/wg0.conf`

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Commit your changes: `git commit -am 'Add feature'`
4. Push to the branch: `git push origin feature-name`
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
