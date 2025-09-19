# NordHero

A command-line tool for managing WireGuard VPN connections through NordVPN servers on Linux systems.

## What it does

NordHero simplifies VPN management by automatically selecting the best NordVPN servers and generating WireGuard configurations. Connect to any NordVPN server with a single command or through an interactive menu.

## Requirements

- Linux operating system
- Python 3.11 or higher
- WireGuard tools installed
- Active NordVPN subscription
- WireGuard private key from NordVPN

## Installation

Install WireGuard tools using your distribution's package manager:

```bash
# Debian/Ubuntu
sudo apt install wireguard-tools

# Fedora
sudo dnf install wireguard-tools

# Arch Linux
sudo pacman -S wireguard-tools
```

Clone and install NordHero:

```bash
git clone https://github.com/nordhero/nordhero.git
cd nordhero
uv sync
```

## Quick Start

1. Get your WireGuard private key from [NordVPN Dashboard](https://my.nordaccount.com/dashboard/nordvpn/manual-configuration/)

2. Run initial setup:
```bash
uv run python main.py --setup-config
```

3. Update server database:
```bash
uv run python main.py --update-servers
```

4. Connect to VPN:
```bash
uv run python main.py --connect
```

## Usage

### Command Line

```bash
# Check connection status
uv run python main.py --status

# Connect to best available server
uv run python main.py --connect

# Connect to specific server
uv run python main.py --connect us1234.nordvpn.com

# Disconnect from VPN
uv run python main.py --disconnect

# Update server list
uv run python main.py --update-servers

# List available servers
uv run python main.py --list-servers

# List servers by country
uv run python main.py --list-servers "United States"
```

### Interactive Menu

Run without arguments to access the interactive menu:

```bash
uv run python main.py
```

Available options:
- Initial setup and configuration
- Update local server database
- Browse and select VPN servers
- Manage connections (connect, disconnect, restart)
- Monitor connection status in real-time
- Configure autostart with systemd

## Docker

### Quick Start with Docker

```bash
# Build the image
docker build -t nordhero .

# Run with environment variables
docker run -it \
  --cap-add=NET_ADMIN \
  --device=/dev/net/tun \
  -e NORDHERO_PRIVATE_KEY="your_private_key_here" \
  -e NORDHERO_CLIENT_IP="10.5.0.2/32" \
  nordhero
```

### Docker Compose

```bash
# Edit docker-compose.yml to set your private key
# Then start the service
docker-compose up -d

# Access the container
docker-compose exec nordhero python main.py
```

## Configuration

Configuration is stored in `config/config.toml`. Key settings:

```toml
[wireguard]
private_key_file = "config/wireguard.key"
client_ip = "10.5.0.2/32"
dns = "103.86.96.100"
persistent_keepalive = 25

[database]
path = "servers.db"
max_load = 100

[output]
config_dir = "/etc/wireguard"
config_wg_file = "/etc/wireguard/wg0.conf"
```

## Troubleshooting

**Permission denied errors**: Ensure your user can run sudo commands for WireGuard management.

**No servers found**: Run `--update-servers` to refresh the local server database.

**Connection fails**: Verify your WireGuard private key is valid and your NordVPN subscription is active.

**Docker networking issues**: Ensure the container has NET_ADMIN capability and access to /dev/net/tun.

## License

MIT License. See LICENSE file for details.