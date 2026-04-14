#!/bin/bash

# Novel Content Audit System - Security Setup Script
# Sets up security configurations, SSL certificates, and secure defaults

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Generate secure random key
generate_secret_key() {
    local length=${1:-64}
    openssl rand -base64 $length | tr -d "=+/" | cut -c1-$length
}

# Setup SSL certificates
setup_ssl_certificates() {
    log "Setting up SSL certificates..."

    local ssl_dir="$PROJECT_ROOT/docker/nginx/ssl"
    mkdir -p "$ssl_dir"

    # Check if certificates already exist
    if [[ -f "$ssl_dir/cert.pem" ]] && [[ -f "$ssl_dir/key.pem" ]]; then
        warning "SSL certificates already exist. Skipping generation."
        return
    fi

    echo -n "Do you want to generate self-signed certificates for development? (y/N): "
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        log "Generating self-signed SSL certificates..."

        # Generate private key
        openssl genrsa -out "$ssl_dir/key.pem" 2048

        # Generate certificate
        openssl req -new -x509 -key "$ssl_dir/key.pem" -out "$ssl_dir/cert.pem" -days 365 \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

        # Set proper permissions
        chmod 600 "$ssl_dir/key.pem"
        chmod 644 "$ssl_dir/cert.pem"

        success "Self-signed SSL certificates generated"
    else
        warning "No SSL certificates generated. Add your own certificates to $ssl_dir/"
        echo "Required files:"
        echo "  - cert.pem (certificate)"
        echo "  - key.pem (private key)"
    fi
}

# Setup environment file with secure defaults
setup_environment_file() {
    log "Setting up production environment file..."

    local env_file="$PROJECT_ROOT/.env.prod"

    if [[ -f "$env_file" ]]; then
        echo -n "Production environment file already exists. Overwrite? (y/N): "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            warning "Skipping environment file setup"
            return
        fi
    fi

    # Copy template
    cp "$PROJECT_ROOT/.env.prod.template" "$env_file"

    # Generate secure keys
    log "Generating secure keys..."
    local secret_key=$(generate_secret_key 64)
    local jwt_key=$(generate_secret_key 64)
    local redis_password=$(generate_secret_key 32)
    local grafana_password=$(generate_secret_key 16)
    local elastic_password=$(generate_secret_key 16)

    # Replace placeholders
    sed -i.bak \
        -e "s/your-super-secret-key-change-this-in-production-minimum-32-characters/$secret_key/g" \
        -e "s/your-jwt-secret-key-change-this-in-production-minimum-32-characters/$jwt_key/g" \
        -e "s/your-redis-password-here/$redis_password/g" \
        -e "s/change-this-secure-password/$grafana_password/g" \
        -e "s/change-this-elastic-password/$elastic_password/g" \
        "$env_file"

    # Remove backup file
    rm -f "$env_file.bak"

    # Set proper permissions
    chmod 600 "$env_file"

    success "Environment file created with secure defaults"

    #  for required values
    echo
    echo "Please edit $env_file and set the following required values:"
    echo "  - OPENAI_API_KEY (your OpenAI API key)"
    echo "  - CORS_ORIGINS (your allowed domains)"
    echo "  - ALLOWED_HOSTS (your allowed hosts)"
    echo "  - S3 backup credentials (if using S3 backups)"
    echo
}

# Setup file permissions
setup_file_permissions() {
    log "Setting up secure file permissions..."

    # Set directory permissions
    find "$PROJECT_ROOT" -type d -exec chmod 755 {} \;

    # Set file permissions
    find "$PROJECT_ROOT" -type f -exec chmod 644 {} \;

    # Make scripts executable
    find "$PROJECT_ROOT/scripts" -name "*.sh" -exec chmod 755 {} \;
    find "$PROJECT_ROOT/scripts" -name "*.py" -exec chmod 755 {} \;

    # Secure sensitive files
    if [[ -f "$PROJECT_ROOT/.env.prod" ]]; then
        chmod 600 "$PROJECT_ROOT/.env.prod"
    fi

    # Secure SSL keys
    if [[ -f "$PROJECT_ROOT/docker/nginx/ssl/key.pem" ]]; then
        chmod 600 "$PROJECT_ROOT/docker/nginx/ssl/key.pem"
    fi

    # Create secure directories
    mkdir -p "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/backups"
    chmod 750 "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/backups"

    success "File permissions configured securely"
}

# Setup Docker security
setup_docker_security() {
    log "Configuring Docker security settings..."

    # Create Docker daemon configuration
    local docker_daemon_config="/etc/docker/daemon.json"

    if [[ -f "$docker_daemon_config" ]]; then
        warning "Docker daemon configuration already exists. Please manually review security settings."
    else
        cat > "/tmp/docker-daemon.json" << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "100m",
        "max-file": "5"
    },
    "live-restore": true,
    "userland-proxy": false,
    "no-new-privileges": true,
    "seccomp-profile": "/etc/docker/seccomp.json",
    "apparmor-profile": "docker-default"
}
EOF

        echo "Docker daemon configuration created at /tmp/docker-daemon.json"
        echo "Please move it to $docker_daemon_config and restart Docker daemon"
    fi

    success "Docker security configuration prepared"
}

# Setup firewall rules (if UFW is available)
setup_firewall() {
    if command -v ufw &> /dev/null; then
        log "Configuring UFW firewall rules..."

        # Allow SSH
        ufw allow 22/tcp comment 'SSH'

        # Allow HTTP/HTTPS
        ufw allow 80/tcp comment 'HTTP'
        ufw allow 443/tcp comment 'HTTPS'

        # Allow monitoring (restrict to specific IPs in production)
        ufw allow 3000/tcp comment 'Grafana'
        ufw allow 9090/tcp comment 'Prometheus'
        ufw allow 5601/tcp comment 'Kibana'

        # Deny all other traffic by default
        ufw default deny incoming
        ufw default allow outgoing

        echo "UFW rules configured. Enable with: sudo ufw enable"
        success "Firewall rules prepared"
    else
        warning "UFW not found. Please configure firewall manually."
    fi
}

# Generate API keys
generate_api_keys() {
    log "Generating API keys..."

    local api_keys_file="$PROJECT_ROOT/api-keys.txt"

    echo "Generated API Keys - $(date)" > "$api_keys_file"
    echo "=========================" >> "$api_keys_file"

    for i in {1..3}; do
        local api_key="novel-$(generate_secret_key 32)"
        echo "API Key $i: $api_key" >> "$api_keys_file"
    done

    chmod 600 "$api_keys_file"

    success "API keys generated in $api_keys_file"
    warning "Store these keys securely and add them to your environment file"
}

# Security audit
security_audit() {
    log "Running security audit..."

    local issues=0

    # Check for insecure files
    if [[ -f "$PROJECT_ROOT/.env" ]] && [[ $(stat -c %a "$PROJECT_ROOT/.env") != "600" ]]; then
        warning "Environment file has insecure permissions"
        ((issues++))
    fi

    # Check for default passwords
    if grep -q "change-this" "$PROJECT_ROOT/.env.prod" 2>/dev/null; then
        warning "Default passwords found in environment file"
        ((issues++))
    fi

    # Check SSL certificate
    if [[ ! -f "$PROJECT_ROOT/docker/nginx/ssl/cert.pem" ]]; then
        warning "SSL certificate not found"
        ((issues++))
    fi

    # Check for exposed secrets
    if find "$PROJECT_ROOT" -name "*.log" -exec grep -l "password\|secret\|key" {} \; | grep -q .; then
        warning "Potential secrets found in log files"
        ((issues++))
    fi

    if [[ $issues -eq 0 ]]; then
        success "Security audit passed with no issues"
    else
        warning "Security audit found $issues potential issues"
    fi

    return $issues
}

# Main setup function
main() {
    echo "=" * 60
    echo "Novel Content Audit System - Security Setup"
    echo "=" * 60

    # Check if running as root
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root for security reasons"
    fi

    # Check required commands
    for cmd in openssl docker docker-compose; do
        if ! command -v $cmd &> /dev/null; then
            error "$cmd is not installed"
        fi
    done

    # Run setup steps
    setup_ssl_certificates
    setup_environment_file
    setup_file_permissions
    setup_docker_security
    setup_firewall
    generate_api_keys

    echo
    log "Running security audit..."
    if security_audit; then
        echo
        success "Security setup completed successfully!"
        echo
        echo "Next steps:"
        echo "1. Review and edit $PROJECT_ROOT/.env.prod"
        echo "2. Add your OpenAI API key and other required configuration"
        echo "3. Move Docker daemon config from /tmp/docker-daemon.json if needed"
        echo "4. Enable firewall: sudo ufw enable"
        echo "5. Review generated API keys in api-keys.txt"
        echo "6. Test deployment with: ./scripts/deploy.sh deploy"
    else
        warning "Security setup completed with some issues. Please review warnings above."
    fi
}

# Show help
show_help() {
    cat << EOF
Novel Content Audit System - Security Setup Script

Usage: $0 [OPTIONS]

Options:
    --ssl-only          Only setup SSL certificates
    --env-only          Only setup environment file
    --audit-only        Only run security audit
    -h, --help          Show this help message

This script will:
- Generate SSL certificates (self-signed for development)
- Create secure environment file with generated keys
- Set proper file permissions
- Configure Docker security settings
- Setup firewall rules (if UFW is available)
- Generate API keys
- Run security audit

EOF
}

# Parse arguments
case "${1:-}" in
    --ssl-only)
        setup_ssl_certificates
        ;;
    --env-only)
        setup_environment_file
        ;;
    --audit-only)
        security_audit
        ;;
    -h|--help)
        show_help
        ;;
    "")
        main
        ;;
    *)
        error "Unknown option: $1"
        ;;
esac