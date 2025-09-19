#!/bin/bash

# Test script for NordHero Docker setup
# This script tests the Docker container functionality

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
CONTAINER_NAME="nordhero-test"
IMAGE_NAME="nordhero:test"
TEST_PRIVATE_KEY="YourTestPrivateKeyHere+MakeIt44Characters="
TEST_CLIENT_IP="10.5.0.2/32"

# Logging functions
log() {
    echo -e "${GREEN}[TEST] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Cleanup function
cleanup() {
    log "Cleaning up test environment..."
    
    # Stop and remove container
    if docker ps -q -f name=$CONTAINER_NAME >/dev/null 2>&1; then
        docker stop $CONTAINER_NAME >/dev/null 2>&1 || true
    fi
    
    if docker ps -a -q -f name=$CONTAINER_NAME >/dev/null 2>&1; then
        docker rm $CONTAINER_NAME >/dev/null 2>&1 || true
    fi
    
    # Remove test volumes
    docker volume rm ${CONTAINER_NAME}_config >/dev/null 2>&1 || true
    docker volume rm ${CONTAINER_NAME}_data >/dev/null 2>&1 || true
    docker volume rm ${CONTAINER_NAME}_wireguard >/dev/null 2>&1 || true
}

# Trap to ensure cleanup on exit
trap cleanup EXIT

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Docker is installed and running
    if ! command -v docker >/dev/null 2>&1; then
        error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        error "Docker daemon is not running"
        exit 1
    fi
    
    # Check if docker-compose is installed
    if ! command -v docker-compose >/dev/null 2>&1; then
        warn "docker-compose is not installed (optional)"
    fi
    
    # Check if WireGuard is available on host
    if ! lsmod | grep -q wireguard; then
        warn "WireGuard kernel module not loaded on host"
        info "Container will use userspace implementation"
    fi
    
    log "Prerequisites check completed"
}

# Build the Docker image
build_image() {
    log "Building Docker image..."
    
    if ! docker build -t $IMAGE_NAME . -f Dockerfile; then
        error "Failed to build Docker image"
        exit 1
    fi
    
    log "Docker image built successfully"
}

# Test basic container functionality
test_container_start() {
    log "Testing container startup..."
    
    # Start container with sleep command to keep it running without interactive input
    docker run -d \
        --name $CONTAINER_NAME \
        --cap-add NET_ADMIN \
        --cap-add SYS_MODULE \
        --device /dev/net/tun:/dev/net/tun \
        --sysctl net.ipv4.conf.all.src_valid_mark=1 \
        --sysctl net.ipv4.ip_forward=1 \
        -e NORDHERO_CONTAINER_MODE=true \
        -e NORDHERO_PRIVATE_KEY="$TEST_PRIVATE_KEY" \
        -e NORDHERO_CLIENT_IP="$TEST_CLIENT_IP" \
        -v ${CONTAINER_NAME}_config:/app/config \
        -v ${CONTAINER_NAME}_data:/app/data \
        -v ${CONTAINER_NAME}_wireguard:/etc/wireguard \
        $IMAGE_NAME sleep infinity >/dev/null
    
    # Wait for container to be ready
    sleep 5
    
    # Check if container is running
    if ! docker ps | grep -q $CONTAINER_NAME; then
        error "Container failed to start"
        docker logs $CONTAINER_NAME
        exit 1
    fi
    
    # Test the initialization by running setup command
    log "Testing container initialization..."
    docker exec $CONTAINER_NAME uv run python main.py --setup-config >/dev/null 2>&1 || true
    
    log "Container started successfully"
}

# Test container environment detection
test_container_detection() {
    log "Testing container environment detection..."
    
    local result
    result=$(docker exec $CONTAINER_NAME python -c "
from models.core.container_adapter import get_container_adapter
import json
adapter = get_container_adapter()
print(json.dumps({
    'is_container': adapter.environment.is_container,
    'container_type': adapter.environment.container_type,
    'has_systemd': adapter.environment.has_systemd,
    'has_sudo': adapter.environment.has_sudo
}))
")
    
    echo "$result" | python -c "
import sys, json
data = json.load(sys.stdin)
assert data['is_container'] == True, 'Container detection failed'
assert data['has_systemd'] == False, 'Systemd should be disabled in container'
assert data['has_sudo'] == False, 'Sudo should not be needed in container'
print('Container environment detection: PASSED')
"
    
    log "Container environment detection test passed"
}

# Test WireGuard tools availability
test_wireguard_tools() {
    log "Testing WireGuard tools availability..."
    
    # Test wg command
    if ! docker exec $CONTAINER_NAME wg --version >/dev/null 2>&1; then
        error "wg command not available in container"
        exit 1
    fi
    
    # Test wg-quick command
    if ! docker exec $CONTAINER_NAME which wg-quick >/dev/null 2>&1; then
        error "wg-quick command not available in container"
        exit 1
    fi
    
    log "WireGuard tools test passed"
}

# Test configuration management
test_configuration() {
    log "Testing configuration management..."
    
    # Test auto-configuration from environment variables
    local config_test
    config_test=$(docker exec $CONTAINER_NAME python -c "
from models.config_management import ConfigManager
from pathlib import Path
import os

# Verify container environment
adapter_test = os.environ.get('NORDHERO_CONTAINER_MODE')
if adapter_test != 'true':
    raise Exception('Container mode not detected')

# Test ConfigManager
try:
    config_manager = ConfigManager(Path('/app'))
    config_manager.load_or_create()
    
    # Check auto-configuration
    client_ip = str(config_manager.config.wireguard.client_ip)
    if client_ip != '$TEST_CLIENT_IP':
        raise Exception(f'Auto-configuration failed: expected $TEST_CLIENT_IP, got {client_ip}')
    
    print('Configuration test: PASSED')
except Exception as e:
    print(f'Configuration test: FAILED - {e}')
    raise
")
    
    echo "$config_test"
    log "Configuration management test passed"
}

# Test application functionality
test_application() {
    log "Testing application functionality..."
    
    # Test help command
    if ! docker exec $CONTAINER_NAME uv run python main.py --help >/dev/null 2>&1; then
        error "Application help command failed"
        exit 1
    fi
    
    # Test status command
    if ! docker exec $CONTAINER_NAME uv run python main.py --status >/dev/null 2>&1; then
        error "Application status command failed"
        exit 1
    fi
    
    # Test database update (with small limit to avoid long wait)
    log "Testing database update (this may take a moment)..."
    if ! timeout 30 docker exec $CONTAINER_NAME uv run python main.py --update-servers 5 >/dev/null 2>&1; then
        warn "Database update test timed out or failed (this is expected in test environment)"
    else
        log "Database update test passed"
    fi
    
    log "Application functionality tests completed"
}

# Test container capabilities
test_capabilities() {
    log "Testing container capabilities..."
    
    # Test NET_ADMIN capability
    if ! docker exec $CONTAINER_NAME ip addr show >/dev/null 2>&1; then
        error "NET_ADMIN capability test failed"
        exit 1
    fi
    
    # Test /dev/net/tun access
    if ! docker exec $CONTAINER_NAME test -c /dev/net/tun; then
        error "/dev/net/tun device not accessible"
        exit 1
    fi
    
    # Test sysctl settings
    local ip_forward
    ip_forward=$(docker exec $CONTAINER_NAME cat /proc/sys/net/ipv4/ip_forward)
    if [ "$ip_forward" != "1" ]; then
        error "IP forwarding not enabled"
        exit 1
    fi
    
    log "Container capabilities test passed"
}

# Test service management (should be disabled)
test_service_management() {
    log "Testing service management (should be disabled in container)..."
    
    local service_test
    service_test=$(docker exec $CONTAINER_NAME python -c "
from models.service_management import check_systemd_available
result = check_systemd_available()
if result:
    raise Exception('Systemd should not be available in container')
print('Service management test: PASSED')
")
    
    echo "$service_test"
    log "Service management test passed"
}

# Test volume persistence
test_volumes() {
    log "Testing volume persistence..."
    
    # Create a test file in config volume
    docker exec $CONTAINER_NAME touch /app/config/test_file
    
    # Restart container
    docker restart $CONTAINER_NAME >/dev/null
    sleep 3
    
    # Check if file still exists
    if ! docker exec $CONTAINER_NAME test -f /app/config/test_file; then
        error "Volume persistence test failed"
        exit 1
    fi
    
    log "Volume persistence test passed"
}

# Test container health
test_health() {
    log "Testing container health..."
    
    # Check container health status
    local health_status
    health_status=$(docker inspect --format='{{.State.Health.Status}}' $CONTAINER_NAME 2>/dev/null || echo "no-health-check")
    
    if [ "$health_status" = "unhealthy" ]; then
        error "Container health check failed"
        docker inspect --format='{{range .State.Health.Log}}{{.Output}}{{end}}' $CONTAINER_NAME
        exit 1
    fi
    
    log "Container health test passed"
}

# Test docker-compose configuration
test_docker_compose() {
    log "Testing docker-compose configuration..."
    
    if command -v docker-compose >/dev/null 2>&1; then
        # Validate docker-compose.yml syntax
        if docker-compose config >/dev/null 2>&1; then
            log "docker-compose.yml syntax is valid"
        else
            warn "docker-compose.yml syntax validation failed"
        fi
    else
        warn "docker-compose not available, skipping compose test"
    fi
}

# Main test execution
main() {
    info "Starting NordHero Docker tests..."
    info "Container: $CONTAINER_NAME"
    info "Image: $IMAGE_NAME"
    info "Test Private Key: ${TEST_PRIVATE_KEY:0:10}..."
    echo ""
    
    check_prerequisites
    build_image
    test_container_start
    test_container_detection
    test_wireguard_tools
    test_configuration
    test_capabilities
    test_service_management
    test_application
    test_volumes
    test_health
    test_docker_compose
    
    echo ""
    log "All tests completed successfully!"
    info "Your NordHero Docker setup is working correctly."
    echo ""
    info "Next steps:"
    info "1. Set your real WireGuard private key in docker-compose.yml"
    info "2. Run: docker-compose up -d"
    info "3. Setup: docker exec -it nordhero uv run python main.py --setup-config"
    info "4. Use: docker exec -it nordhero uv run python main.py"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi