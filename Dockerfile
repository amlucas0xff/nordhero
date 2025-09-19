# NordHero WireGuard Manager Docker Image with uv
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    NORDHERO_CONTAINER_MODE=true \
    NORDHERO_CONFIG_PATH=/app/config \
    NORDHERO_DATABASE_PATH=/app/data/servers.db \
    NORDHERO_WG_CONFIG_PATH=/etc/wireguard/wg0.conf

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # WireGuard and networking tools
    wireguard-tools \
    iproute2 \
    iptables \
    iputils-ping \
    curl \
    # Process and system tools
    procps \
    psmisc \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories with proper permissions
RUN mkdir -p /app/config \
    && mkdir -p /app/data \
    && mkdir -p /etc/wireguard \
    && mkdir -p /var/log/nordhero \
    && chmod 755 /app/config \
    && chmod 755 /app/data \
    && chmod 755 /etc/wireguard

# Copy uv configuration and install Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Copy and set up entry point script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create a non-root user (but we'll run as root for network management)
RUN useradd --create-home --shell /bin/bash nordhero

# Set proper ownership for application directories
RUN chown -R nordhero:nordhero /app \
    && chown -R nordhero:nordhero /var/log/nordhero

# Expose any ports if needed (for future web UI)
EXPOSE 8080

# Health check to verify WireGuard tools are available
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wg --version || exit 1

# Set volumes for persistent data
VOLUME ["/app/config", "/app/data", "/etc/wireguard"]

# Entry point
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command (interactive menu)
CMD ["uv", "run", "python", "main.py"]