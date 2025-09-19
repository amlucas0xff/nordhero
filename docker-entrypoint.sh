#!/bin/bash
set -e

# NordHero Docker Entry Point Script
# This script initializes the container environment and manages the application lifecycle

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" >&2
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" >&2
}

# Signal handlers for graceful shutdown
cleanup() {
    log "Received termination signal, cleaning up..."
    
    # Disconnect WireGuard if connected
    if [ -f /etc/wireguard/wg0.conf ]; then
        log "Checking WireGuard connection status..."
        if wg show wg0 >/dev/null 2>&1; then
            log "Disconnecting WireGuard..."
            wg-quick down wg0 || warn "Failed to disconnect WireGuard cleanly"
        fi
    fi
    
    # Kill any background processes
    local pids=$(jobs -pr)
    if [ -n "$pids" ]; then
        log "Terminating background processes..."
        kill $pids 2>/dev/null || true
    fi
    
    log "Cleanup completed"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT SIGQUIT

# Validate environment
validate_environment() {
    log "Validating container environment..."
    
    # Check if running as root (required for WireGuard)
    if [ "$(id -u)" != "0" ]; then
        error "Container must run as root for WireGuard management"
        exit 1
    fi
    
    # Check WireGuard tools
    if ! command -v wg >/dev/null 2>&1; then
        error "WireGuard tools not found"
        exit 1
    fi
    
    if ! command -v wg-quick >/dev/null 2>&1; then
        error "wg-quick not found"
        exit 1
    fi
    
    log "Environment validation passed"
}

# Setup container environment
setup_environment() {
    log "Setting up container environment..."
    
    # Create necessary directories
    mkdir -p "${NORDHERO_CONFIG_PATH}" || error "Failed to create config directory"
    mkdir -p "$(dirname "${NORDHERO_DATABASE_PATH}")" || error "Failed to create data directory"
    mkdir -p "$(dirname "${NORDHERO_WG_CONFIG_PATH}")" || error "Failed to create wireguard directory"
    mkdir -p /var/log/nordhero || error "Failed to create log directory"
    
    # Set permissions
    chmod 755 "${NORDHERO_CONFIG_PATH}"
    chmod 755 "$(dirname "${NORDHERO_DATABASE_PATH}")"
    chmod 755 "$(dirname "${NORDHERO_WG_CONFIG_PATH}")"
    chmod 755 /var/log/nordhero
    
    # Load WireGuard kernel module if not loaded
    if ! lsmod | grep -q wireguard; then
        log "Loading WireGuard kernel module..."
        if ! modprobe wireguard; then
            warn "Failed to load WireGuard kernel module - will use userspace implementation"
        fi
    fi
    
    # Enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward || warn "Failed to enable IP forwarding"
    
    log "Environment setup completed"
}

# Check for first-time setup
check_first_run() {
    local config_file="${NORDHERO_CONFIG_PATH}/config.toml"
    
    if [ ! -f "$config_file" ]; then
        log "First run detected - configuration needed"
        
        # Check if environment variables are provided for auto-setup
        if [ -n "$NORDHERO_PRIVATE_KEY" ] && [ -n "$NORDHERO_CLIENT_IP" ]; then
            log "Auto-configuring from environment variables..."
            auto_configure
        else
            warn "No configuration found and no environment variables provided"
            warn "You'll need to run setup manually:"
            warn "  docker exec -it <container> uv run python main.py --setup-config"
        fi
    else
        log "Configuration file found: $config_file"
    fi
}

# Auto-configure from environment variables
auto_configure() {
    log "Performing automatic configuration..."
    
    local config_file="${NORDHERO_CONFIG_PATH}/config.toml"
    local key_file="${NORDHERO_CONFIG_PATH}/wireguard.key"
    
    # Create private key file
    echo "$NORDHERO_PRIVATE_KEY" > "$key_file"
    chmod 600 "$key_file"
    
    # Create basic configuration
    cat > "$config_file" << EOF
[wireguard]
private_key_file = "$key_file"
client_ip = "${NORDHERO_CLIENT_IP:-10.5.0.2/32}"
dns = "${NORDHERO_DNS:-103.86.96.100}"
persistent_keepalive = ${NORDHERO_KEEPALIVE:-25}

[database]
path = "$NORDHERO_DATABASE_PATH"
max_load = ${NORDHERO_MAX_LOAD:-100}
default_limit = ${NORDHERO_DEFAULT_LIMIT:-0}

[output]
config_dir = "$(dirname "$NORDHERO_WG_CONFIG_PATH")"
config_wg_file = "$NORDHERO_WG_CONFIG_PATH"
EOF
    
    chmod 600 "$config_file"
    log "Auto-configuration completed"
}

# Display startup information
show_startup_info() {
    echo -e "${BLUE}"
    echo "=================================================="
    echo "     NordHero WireGuard Manager Container"
    echo "=================================================="
    echo -e "${NC}"
    log "Container initialized successfully"
    log "Configuration path: ${NORDHERO_CONFIG_PATH}"
    log "Database path: ${NORDHERO_DATABASE_PATH}"
    log "WireGuard config: ${NORDHERO_WG_CONFIG_PATH}"
    
    if [ "$#" -gt 0 ]; then
        log "Running command: $*"
    else
        log "Starting interactive mode..."
    fi
    echo ""
}

# Main initialization
main() {
    log "Starting NordHero container initialization..."
    
    validate_environment
    setup_environment
    check_first_run
    show_startup_info "$@"
    
    # If no command provided, run default
    if [ "$#" -eq 0 ]; then
        set -- "uv" "run" "python" "main.py"
    fi
    
    # Execute the main command
    log "Executing: $*"
    exec "$@"
}

# Run main function with all arguments
main "$@"